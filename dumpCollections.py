#!/usr/local/bin/python3
from __future__ import annotations


# dumpCollections
# Original GitHub project: https://github.com/auino/cookidump

import argparse
import base64
import io
import json
import locale
import os
import platform
import re
import sys
import time
import traceback
import pprint
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Optional, Dict, List
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from urllib.parse import urlparse

# Import our data models and configuration
try:
    # Try relative imports first (when used as module)
    from .models import Collection, Recipe, RecipeState
except ImportError:
    # Fallback to absolute imports (when run as script)
    from models import Collection, Recipe, RecipeState
    from configuration import (
        ScrapingConfiguration, BrowserConfiguration, ThreadingConfiguration,
        ConfigurationManager
    )


class ThreadSafePageLogger:
    """Thread-safe logger for page fetches and timing information."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._file_lock = threading.Lock()
                    cls._instance._log_file = 'log.txt'
                    # Per-thread timing state: {thread_id: last_timestamp}
                    cls._instance._thread_timings = {}
                    cls._instance._timing_lock = threading.Lock()
        return cls._instance

    def log_page_get(self, url: str):
        """Log a page fetch with timestamp in a thread-safe manner."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        log_entry = f"{timestamp} - {url}\n"

        with self._file_lock:
            with open(self._log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)

    def log_timing(self, operation: str, context: str = ""):
        """
        Log timing information with elapsed time since last log in this thread.

        Args:
            operation: Description of the operation being timed
            context: Additional context (e.g., recipe name, collection name)
        """
        thread_id = threading.get_ident()
        now = datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        # Calculate elapsed time since last log in this thread
        with self._timing_lock:
            last_time = self._thread_timings.get(thread_id)
            if last_time is not None:
                elapsed_ms = (now - last_time).total_seconds() * 1000
                elapsed_str = f"+{elapsed_ms:.1f}ms"
            else:
                elapsed_str = "+0.0ms"
            self._thread_timings[thread_id] = now

        # Format log entry
        if context:
            log_entry = f"{timestamp} - Thread-{thread_id} [{elapsed_str}] {operation}: {context}\n"
        else:
            log_entry = f"{timestamp} - Thread-{thread_id} [{elapsed_str}] {operation}\n"

        with self._file_lock:
            with open(self._log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)


# Global logger instance
_page_logger = ThreadSafePageLogger()


def logged_driver_get(driver, url: str):
    """Wrapper for driver.get() that logs the page fetch."""
    _page_logger.log_page_get(url)
    return driver.get(url)



def parse_main_args() -> argparse.Namespace:
    """Parse command line arguments (shared function)."""
    parser = argparse.ArgumentParser(description='Dump Cookidoo recipes from a valid account')
    parser.add_argument('-l','--locale')
    parser.add_argument('-p','--pattern')
    parser.add_argument('-j','--json')
    parser.add_argument('-s','--saved', action='store_true')
    parser.add_argument('webdriverfile', type=str, help='the path to the Chrome WebDriver file')
    parser.add_argument('outputdir', type=str, help='the output directory')
    parser.add_argument('--headless', action='store_true',
                    help='runs Chrome in headless mode, needs cookies.json saved with --save-cookies previously. Default: \'False\'')
    parser.add_argument('--save-cookies', action='store_true',
                    help='store cookies in local cookies.json file then exits; to be used with --headless or to avoid login on subsequent runs')
    parser.add_argument('--max-threads', type=int, default=3,
                    help='maximum number of collection threads for parallel processing (default: 3)')
    return parser.parse_args()




class ThreadSafeBrowserManager:
    """Manages browser instances for threads with authentication."""

    def __init__(self, config: ScrapingConfiguration, cookies_data: Optional[List[Dict]] = None):
        self.config = config
        self.cookies_data = cookies_data
        self._lock = threading.Lock()

    def create_authenticated_driver(self):
        """Create a new browser instance with authentication using enhanced configuration."""
        browser_config = BrowserConfiguration.from_scraping_config(self.config)

        options = Options()

        # Apply browser configuration
        if browser_config.headless:
            options.add_argument("--headless")
            options.add_argument("start-maximized")

        # Window size
        options.add_argument(f"--window-size={browser_config.window_size[0]},{browser_config.window_size[1]}")

        # User agent
        if browser_config.user_agent:
            options.add_argument(f"--user-agent={browser_config.user_agent}")

        # Performance and resource options
        if browser_config.disable_images:
            options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})

        if browser_config.disable_dev_shm_usage:
            options.add_argument("--disable-dev-shm-usage")

        if browser_config.disable_gpu:
            options.add_argument("--disable-gpu")

        if browser_config.no_sandbox:
            options.add_argument("--no-sandbox")

        service = Service(self.config.webdriver_path)
        driver = webdriver.Chrome(service=service, options=options)

        # Set timeouts from configuration
        driver.set_page_load_timeout(browser_config.page_load_timeout)
        driver.implicitly_wait(browser_config.implicit_wait)

        # Apply cookies for authentication if available
        if self.cookies_data:
            logged_driver_get(driver, self.config.base_url)
            for cookie in self.cookies_data:
                try:
                    driver.add_cookie(cookie)
                except:
                    pass  # Some cookies may not be valid for this context

        return driver

    def close_driver(self, driver):
        """Safely close a browser instance."""
        try:
            driver.quit()
        except:
            pass  # Driver may already be closed


class ThreadSafeResultCollector:
    """Thread-safe collector for processing results with memory management."""

    def __init__(self):
        self._lock = threading.Lock()
        self.recipe_states: Dict[str, RecipeState] = {}
        self.processed_collections = 0
        self.processed_recipes = 0
        self.errors: List[str] = []

    def mark_recipe_for_processing(self, recipe_id: str) -> bool:
        """
        Mark recipe for processing. Returns True if should process, False if already processed.
        Thread-safe and ensures each recipe is only processed once.
        """
        with self._lock:
            current_state = self.recipe_states.get(recipe_id, None)

            if current_state is None:
                # First time seeing this recipe - mark it for processing
                self.recipe_states[recipe_id] = RecipeState.FULL_DATA_LOADED
                return True
            else:
                # Already processed or in progress
                return False

    def mark_recipe_json_exported(self, recipe_id: str):
        """Mark that JSON has been exported for this recipe."""
        with self._lock:
            if recipe_id in self.recipe_states:
                self.recipe_states[recipe_id] = RecipeState.JSON_EXPORTED

    def can_clear_memory(self, recipe_id: str) -> bool:
        """Check if recipe memory can be safely cleared."""
        with self._lock:
            state = self.recipe_states.get(recipe_id)
            return state == RecipeState.JSON_EXPORTED

    def mark_recipe_memory_cleared(self, recipe_id: str):
        """Mark that recipe memory has been cleared."""
        with self._lock:
            if recipe_id in self.recipe_states:
                self.recipe_states[recipe_id] = RecipeState.MEMORY_CLEARED

    def get_recipe_state(self, recipe_id: str) -> Optional[RecipeState]:
        """Get current state of a recipe."""
        with self._lock:
            return self.recipe_states.get(recipe_id)

    def get_memory_stats(self) -> Dict[str, int]:
        """Get memory management statistics."""
        with self._lock:
            stats = {
                'total_recipes': len(self.recipe_states),
                'full_data': 0,
                'json_exported': 0,
                'memory_cleared': 0
            }

            for state in self.recipe_states.values():
                if state == RecipeState.FULL_DATA_LOADED:
                    stats['full_data'] += 1
                elif state == RecipeState.JSON_EXPORTED:
                    stats['json_exported'] += 1
                elif state == RecipeState.MEMORY_CLEARED:
                    stats['memory_cleared'] += 1

            return stats


    def increment_counters(self, collections: int = 0, recipes: int = 0):
        """Thread-safe counter increments."""
        with self._lock:
            self.processed_collections += collections
            self.processed_recipes += recipes

    def add_error(self, error_msg: str):
        """Thread-safe error logging."""
        with self._lock:
            self.errors.append(error_msg)
            print(f"Error: {error_msg}")

    def get_stats(self) -> tuple:
        """Get current statistics thread-safely."""
        with self._lock:
            return self.processed_collections, self.processed_recipes, len(self.errors)


class ScraperSetup:
    """Single-threaded scraper used for initialization and shared methods."""


    def __init__(self, config: ScrapingConfiguration):
        print('Welcome to cookidump, starting things off...')

        self.config = config
        self.base_url: Optional[str] = None
        self.collections_page: Optional[str] = None

        # Start browser using configuration
        self.driver = self._start_browser()
        self.output_dir = config.output_dir
        self.login()

        # read and save the list of valid categories
        with open('categories.txt', 'r') as f:
            self.validCategories = dict.fromkeys(list(filter(lambda line: line[0] != '-', [line.strip() for line in f.read().splitlines()])),'1')


    # ---------- Browser setup ----------

    def _start_browser(self) -> webdriver.Chrome:
        """Start Chrome with configured options (using same configuration as threaded drivers)."""
        browser_config = BrowserConfiguration.from_scraping_config(self.config)

        options = Options()

        # Apply browser configuration (same as ThreadSafeBrowserManager)
        if browser_config.headless:
            options.add_argument("--headless")
            options.add_argument("start-maximized")

        # Window size
        options.add_argument(f"--window-size={browser_config.window_size[0]},{browser_config.window_size[1]}")

        # User agent
        if browser_config.user_agent:
            options.add_argument(f"--user-agent={browser_config.user_agent}")

        # Performance and resource options
        if browser_config.disable_images:
            options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})

        if browser_config.disable_dev_shm_usage:
            options.add_argument("--disable-dev-shm-usage")

        if browser_config.disable_gpu:
            options.add_argument("--disable-gpu")

        if browser_config.no_sandbox:
            options.add_argument("--no-sandbox")

        service = Service(self.config.webdriver_path)
        driver = webdriver.Chrome(service=service, options=options)

        # Set timeouts from configuration
        driver.set_page_load_timeout(browser_config.page_load_timeout)
        driver.implicitly_wait(browser_config.implicit_wait)

        return driver

    def isAuthenticated(self):
        return self.driver.get_cookie("v-authenticated") is not None

    def close(self):
        """Close browser cleanly."""
        print("Closing browser session")
        self.driver.quit()

    def login(self):
        print('Logging in ...')

        # Read cookies (to get user name and password)
        if not self.config.save_cookies_only:
            try:
                with open('cookies.json', 'r') as infile:
                    cookies = json.load(infile)
                    print('cookies.json file found and parsed')
            except FileNotFoundError:
                print('No cookies file found')
                cookies = None
            except Exception as e:
                print(f'Error {e}: cookies.json file not valid, please check - or delete - it, and run with --save-cookies again')
                exit(-1)
        else:
            cookies = None

        # opening the home page
        if self.config.locale is None:
            code = locale.getlocale()[0]
        else:
            code = self.config.locale
        code = code.replace('_','-')
        country = code.split('-')[1]

        match country:
            case 'US': self.base_url = 'https://cookidoo.thermomix.com'
            case 'GB': self.base_url = 'https://cookidoo.co.uk'
            case 'AU': self.base_url = 'https://cookidoo.com.au'
            case _:    self.base_url = 'https://cookidoo.{}'.format(country.lower())

        print(f'The Cookidoo base URL for this locale is {self.base_url}')
        self.collections_page = '{}/organize/{}/my-recipes'.format(self.base_url,code)
        print(f'My recipes are at {self.collections_page}')

        # Go to first page - the Collections page, then log in if necessary
        logged_driver_get(self.driver, self.base_url)

        # Authenticate
        if (cookies is not None):
            # inject cookies
            print('Injecting cookies')
            for cookie in cookies:
                try: self.driver.add_cookie(cookie)
                except: pass
        else:
            print('Cookies not found, proceeding with login')

        logged_driver_get(self.driver, self.collections_page)
        while (not self.isAuthenticated() or self.driver.title == 'Sign in' or self.driver.title == 'Login'):
            logged_driver_get(self.driver, self.base_url+'/profile/login')
            print(f'Browser page title is {self.driver.title}')
            if 'CAPTCHA' in self.driver.page_source:
                print('Error: CAPTCHA detected, please login manually and then run cookidump with --save-cookies')
                exit(-1)
            if cookies is None:
                self.driver.find_element(By.ID, 'username').send_keys(input('Enter your username (email): '))
                self.driver.find_element(By.ID, 'password').send_keys(getpass('Enter your password: '))
                self.driver.find_element(By.XPATH, "//button[contains(text(),'Login')]").click()
            print('Not authenticated, trying again')
            cookies = None
            self.config.save_cookies_only = True
            logged_driver_get(self.driver, self.base_url)
        print(f'Browser page title is now {self.driver.title}')

        # Save authentication cookie for later sessions
        if self.config.save_cookies_only:
            with open('cookies.json', 'w') as outfile: json.dump(self.driver.get_cookies(), outfile)
            print('Cookies saved to cookies.json')

        # Reload page in case login tooks us elsewhere
        logged_driver_get(self.driver, self.collections_page)

        # Verify we're actually authenticated and on the correct page
        if not self.isAuthenticated():
            print('Error: Authentication failed - cookies may be expired or invalid')
            print('Please delete cookies.json and run with --save-cookies to re-authenticate')
            exit(-1)

        if self.driver.title in ['Sign in', 'Login', 'Anmelden']:  # Add more languages if needed
            print(f'Error: Still on login page after authentication (title: {self.driver.title})')
            print('Please delete cookies.json and run with --save-cookies to re-authenticate')
            exit(-1)

        # clicking on cookie accept
        try: self.driver.find_element(By.CLASS_NAME, 'accept-cookie-container').click()
        except:
            # clicking on cookie reject
            try: self.driver.find_element(By.ID, 'onetrust-reject-all-handler').click()
            except: pass
        print('Proceeding with scraping')


    # ------------- Utility methods ----------------

    @staticmethod
    def save_text(output_dir: Path, filename: str, text: str, expected_lines: Optional[int] = None):
        """Save text into a UTF-8 file."""
        path = output_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

        if expected_lines is not None:
            lines = text.count("\n")
            if lines != expected_lines:
                print(f"*** Warning: {filename} has {lines} lines, expected {expected_lines}")

    @staticmethod
    def save_json(output_dir: Path, json_dir: str, filename: str, data: dict):
        """Save JSON data, filtering out empty values."""
        path = output_dir / json_dir / f"{filename}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        cleaned = {k: v for k, v in data.items() if v}
        path.write_text(json.dumps(cleaned, indent=4, sort_keys=True), encoding="utf-8")

    @staticmethod
    def download_image_to_base64(img_url: str) -> str:
        """Download image from URL and return as base64 encoded string."""
        import urllib.request
        import base64

        try:
            with urllib.request.urlopen(img_url) as response:
                image_data = response.read()
                return base64.b64encode(image_data).decode('ascii')
        except Exception as e:
            print(f"Warning: Failed to download image from {img_url}: {e}")
            return ""

    # ------------- Local scraper methods ----------------

    def populateCollectionData(self, driver, collection: Collection, config: ScrapingConfiguration = None) -> Collection:
        """Populate Collection dataclass with all collection information from the current page."""
        try:
            # Scroll to load all recipes for custom collections
            if collection.colltype == 'custom':
                pane = driver.find_element(By.TAG_NAME,'organize-paged-content')
                self.scrollToEnd(driver)

            # Get page HTML and parse with lxml (faster than multiple Selenium calls)
            page_html = driver.page_source

            # Get base URL for converting relative URLs
            active_config = config if config else self.config
            base_url = active_config.base_url if hasattr(active_config, 'base_url') else driver.current_url

            # Parse collection tiles with lxml
            recipe_tiles = parse_collection_tiles_with_lxml(page_html, collection.colltype, base_url)

            print(f'Found {len(recipe_tiles)} recipes in collection {collection.title}')
            collection.actual_recipe_count = len(recipe_tiles)

            # For saved collections, extract the header count for comparison
            if collection.colltype == 'saved':
                try:
                    cnt = int(re.sub(r' Recipes?','',driver.find_element(By.CLASS_NAME,'cdp-header__count').text))
                    collection.header_recipe_count = cnt
                    if cnt != len(recipe_tiles):
                        print(f'Recipe count mismatch for collection {collection.title}: {cnt} in header, but {len(recipe_tiles)} on page')
                except:
                    pass  # No header count available

        except Exception as e:
            print(f'Error parsing collection {collection.title}: {e}')
            recipe_tiles = []
            collection.actual_recipe_count = 0

        # Use pre-compiled recipe pattern from configuration
        recipePattern = config.recipe_pattern if config else self.config.recipe_pattern
        active_config = config if config else self.config

        # Process all recipes in the collection
        for recipe_id, recipe_name, recipe_url in recipe_tiles:
            recipe = Recipe(recipe_id, recipe_name, recipe_url)
            collection.all_recipes.append(recipe)

            # Add to JSON export list if it matches the pattern and collection is not excluded
            should_add_to_json = (
                active_config.json_export and
                (active_config.pattern is None or (recipePattern is not None and recipePattern.search(recipe_name) is not None))
            )

            # Check if collection should be excluded from JSON export
            if should_add_to_json:
                if ConfigurationManager.is_collection_excluded_from_json(active_config, collection.title):
                    should_add_to_json = False

            if should_add_to_json:
                collection.json_recipes.append(recipe)

        # Generate text representation of all recipes for file output
        recipe_lines = []
        for recipe in sorted(collection.all_recipes, key=lambda c: c.id):
            recipe_lines.append(f'{recipe.id}\t{recipe.url}\t{recipe.title}')
        collection.recipe_list_text = '\n'.join(recipe_lines)
        if collection.recipe_list_text:
            collection.recipe_list_text += '\n'  # Add final newline

        # Log collection exclusion information
        if config is not None and ConfigurationManager.is_collection_excluded_from_json(config, collection.title):
            excluded_count = len(collection.all_recipes) - len(collection.json_recipes)
            if excluded_count > 0:
                print(f"Collection '{collection.title}' excluded from JSON export ({excluded_count} recipes excluded)")

        return collection


    def populateRecipeData(self, driver, recipe: Recipe, collection_type: str) -> Recipe:
        """Populate Recipe dataclass with all recipe information from the current page."""
        # Set basic source information
        recipe.source_url = recipe.url
        recipe.language = driver.find_element(By.TAG_NAME,'html').get_attribute('lang')
        recipe.title = driver.find_element(By.CLASS_NAME,"recipe-card__name").text

        # Set source and categories based on collection type
        if collection_type == 'created':
            recipe.categories = ["Thermomix","Created Recipes"]
            recipe.source = "Cookidoo - Created Recipe"
        else:
            recipe.categories = ["Thermomix","Cookidoo Recipes"]
            recipe.source = "Cookidoo"

        # Extract ingredients with lxml (fast local parsing)
        ingredsSection = driver.find_element(By.ID,'ingredients-section')
        section_html = ingredsSection.get_attribute('innerHTML')
        ingredient_texts = parse_ingredients_with_lxml(section_html)
        recipe.ingredients = re.sub(r'\n>>>or',r'\n   or',fixText("\n".join(ingredient_texts)).strip())

        # Extract directions with lxml
        directionsSection = driver.find_element(By.ID,'preparation-steps-section')
        directions_html = directionsSection.get_attribute('innerHTML')
        direction_texts = parse_directions_with_lxml(directions_html)
        recipe.directions = fixText("\n\n".join(direction_texts)).strip()
        if re.search(u'[\uE000-\uE999]',recipe.directions):
            print(f"** Warning: private Unicode chars left in directions for recipe {recipe.title}")

        # Extract My Notes section
        recipe.mynotes = fixText("\n\n".join([li.text.strip() for li in xpathByClass(driver,'//p','core-note__text','')]))

        # Extract timing and serving information
        cook_params = {
            l.get_attribute('class').split()[1] :
            l.find_element(By.XPATH,"./following-sibling::span").text.strip()
            for l in xpathByClass(driver,'//*','recipe-card__cook-params',"//div//span[contains(@class,'icon')]")}

        prep_time = cook_params.get('icon--time-preparation', '-')
        if prep_time != '-':
            recipe.prep_time = re.sub(r'^Prep\.* *','',fixTime(prep_time))

        total_time = cook_params.get('icon--time', '-')
        if total_time != '-':
            recipe.total_time = re.sub(r'Total *','',fixTime(total_time))

        servings = cook_params.get('icon--servings', '-')
        if servings != '-':
            recipe.servings = fixText(servings)

        # Extract recipe-type specific information
        if collection_type == 'created':
            recipe.notes = fixText("\n\n".join([re.sub(r' +', ' ', p.text).strip() for p in driver.find_elements(By.CSS_SELECTOR,'#tips-section p')]))
            importedFrom = driver.find_elements(By.CLASS_NAME,'cr-author-card__link')
            if 'Imported ' not in recipe.notes or len(importedFrom) != 0:
                imported = ''
                if (importedBy := xpathByClass(driver,'//*','cr-author-card__heading-group','//core-user-name')) is not None:
                    imported += " by " + importedBy[0].text
                if len(importedFrom) != 0:
                    imported += " from " + importedFrom[0].get_attribute('href')
                if imported != '':
                    recipe.notes = 'Imported' + imported + "\n\n" + recipe.notes

            # Extract categories from notes for created recipes
            if (catsearch := re.search(r'.*Categories:\s*([^.]+)([.][\s\S]*)?$',recipe.notes)) is not None:
                recipe.categories += re.split(r',\s*',catsearch.group(1))
                for category in recipe.categories:
                    if category not in self.validCategories:
                        print(f"** Unrecognized category {category} found in {recipe.title}")
            else:
                print("** No categories found in notes for",recipe.title)
        else:
            # For saved recipes
            recipe.tags = [a.text.replace('#','').replace('\n','').strip().lower() for a in xpathByClass(driver,'//*','core-tags-wrapper__tags-container','//a')]
            recipe.notes = fixText("\n\n".join(
                [re.sub(r' +', ' ', li.text).strip() for li in driver.find_elements(By.XPATH,"//*[@id='tips-section']//li")]))
            recipe.scaling = [a.text for a in xpathByClass(driver,'//*','rdp-serving-size__variants-section','/core-toggle-button/a')]

        # Add device information
        getDevices(driver, recipe, recipe)

        # Extract and download image data
        try:
            img_url = driver.find_element(By.CLASS_NAME, 'recipe-card__image').get_attribute('src')
            recipe.photo_data = ScraperSetup.download_image_to_base64(img_url)
            recipe.photos = [{'filename': recipe.id + '.jpg', 'name': "1", 'data': recipe.photo_data}]
        except Exception as e:
            print(f"Warning: Failed to extract image for recipe {recipe.title}: {e}")
            recipe.photo_data = ""
            recipe.photos = []

        return recipe

    def recipeToJSON(self, recipe: Recipe) -> dict:
        """Converts a populated Recipe dataclass to Paprika 3 compatible JSON format."""
        # Validate that memory hasn't been cleared before JSON export
        if recipe.is_memory_cleared():
            raise ValueError(f"Cannot export JSON for recipe {recipe.id} - memory has been cleared")

        recipeJson = {}

        # Basic information
        recipeJson['source'] = recipe.source
        recipeJson['source_url'] = recipe.source_url
        recipeJson['language'] = recipe.language
        recipeJson['name'] = recipe.title
        recipeJson['categories'] = recipe.categories.copy()

        # Content
        recipeJson['ingredients'] = recipe.ingredients
        recipeJson['directions'] = recipe.directions
        recipeJson['notes'] = recipe.notes
        recipeJson['mynotes'] = recipe.mynotes

        # Tags and scaling (for saved recipes)
        if recipe.tags:
            recipeJson['tags'] = recipe.tags
        if recipe.scaling:
            recipeJson['scaling'] = recipe.scaling

        # Timing and serving
        if recipe.prep_time:
            recipeJson['prep_time'] = recipe.prep_time
        if recipe.total_time:
            recipeJson['total_time'] = recipe.total_time
        if recipe.servings:
            recipeJson['servings'] = recipe.servings

        # Image data
        recipeJson['photo_data'] = recipe.photo_data
        recipeJson['photos'] = recipe.photos

        return recipeJson

    def doScroll(self, driver, scroll_delay: float = 1.0):
        """Scroll page with configurable delay."""
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            driver.execute_script("window.scrollBy(0,71)", "")
            time.sleep(scroll_delay)
            driver.execute_script("window.scrollBy(0,833)", "")
        except:
            pass  # Scroll exceptions are expected and not critical
        try:
            body = driver.find_element(By.TAG_NAME, 'body')
            body.send_keys(Keys.PAGE_DOWN)
            body.send_keys(Keys.DOWN)
        except:
            pass  # Page down failure is not critical
        time.sleep(scroll_delay)
        try: driver.find_element(By.ID,'scrollResult')
        except: pass


    def scrollToEnd(self, driver, config=None):
        """Scroll to end of page with configurable delays and retry limits."""
        scroll_delay = config.scroll_delay if config else 1.0
        max_retries = config.max_scroll_retries if config else 3

        previousElements = 0
        count = 0
        while True:
            self.doScroll(driver, scroll_delay)
            tiles = driver.find_elements(By.TAG_NAME,'core-tile')
            currentElements = len(tiles)
            name = tiles[currentElements-1].find_element(By.CLASS_NAME,'core-tile__description-text')
            driver.execute_script("arguments[0].scrollIntoView();",name)
            tiles = driver.find_elements(By.TAG_NAME,'core-tile')
            currentElements = len(tiles)
            if previousElements == currentElements:
                try:
                    # clicking on the "load more recipes" button
                    driver.find_element(By.ID,'load-more--button').click()
                    pass  # Load more button clicked
                except:
                    if currentElements % 15 != 0: break
                    count = count + 1
                    if count >= max_retries: break
                self.doScroll(driver, scroll_delay)
                currentElements = len(driver.find_elements(By.TAG_NAME,'core-tile'))
            else:
                count = 0
            pass  # Scrolling progress - no longer needed to debug
            previousElements = currentElements



    def getCustomCollections(self, driver):
        """Scrapes names and URLs of my own custom collections"""
        try:
            collectionList = driver.find_element(By.ID,'filter--created')
        except:
            print(f'Cannot find filter--created in {driver.page_source}')
            exit(-1)
        collections = []
        els = collectionList.find_elements(By.CLASS_NAME,'dropzone')
        for el in els:
            driver.execute_script("arguments[0].scrollIntoView();",el)
            collectionName = el.find_element(By.TAG_NAME,'organize-title').text.strip()
            cURLs = el.find_elements(By.TAG_NAME,'a')
            cURL = cURLs[0]
            collectionURL = cURL.get_attribute('href')
            #print(f'Found custom collection {collectionName} at {collectionURL}')
            collections.append(Collection(collectionName,collectionURL,'custom'))
        return collections


    def getFixedCollections(self, driver):
        """Return name and URL of my bookmarks, and my single 'Created recipe' collection """
        collectionList = driver.find_element(By.CLASS_NAME,'list-all')
        els = collectionList.find_elements(By.XPATH,"//a[@data-type='bookmarklist']")
        collections = [Collection("Bookmarks",els[0].get_attribute('href'),"bookmark")]
        els = collectionList.find_elements(By.XPATH,"//li[@class='is-customer-recipe']//a")
        collections.append(Collection("Created recipes",els[0].get_attribute('href'),"created"))
        return collections


    def getSavedCollections(self, driver):
        """Scrapes names and absolute URLs of a Cookidoo saved collection"""
        collectionDiv = driver.find_element(By.CLASS_NAME,'collection-wrapper')
        collectionRef = collectionDiv.find_element(By.CLASS_NAME,'core-list-cell__wrapper')
        logged_driver_get(driver, collectionRef.get_attribute('href'))
        collectionList = driver.find_element(By.TAG_NAME,'core-tiles-list')
        self.scrollToEnd(driver)
        collections = []
        els = collectionList.find_elements(By.TAG_NAME,'core-tile')
        #print(f'Found {len(els)} saved collections')
        for el in els:
            driver.execute_script("arguments[0].scrollIntoView();",el)
            collectionName = el.find_element(By.CLASS_NAME,'core-tile__description-text').text
            collectionURL = re.sub(r'.*/','https://cookidoo.thermomix.com/collection/en-US/p/',el.find_element(By.TAG_NAME,'a').get_attribute('href'))
            # Saved collection names are not necessarily unique,
            # so append the ID from the URL, minus any anchor
            collectionName += re.sub(r'.*/([^#]+)(#main)?',r' (\1)',collectionURL)
            #print('Found saved collection {collectionName} at {collectionURL}')
            collections.append(Collection(collectionName,collectionURL,'saved'))
        return collections



    def _handle_custom_collection_counts(self, collections):
        """Handle the custom collection counts extraction (for MultiThreadedCookidooScraper)."""
        # Get count of recipes in custom collections
        collectionsByName = {}
        for collection in collections:
            if collection.colltype == 'custom':
                collname = collection.title
                if collname in collectionsByName:
                    print(f'Duplicate name for custom collection {collname} - counts unreliable!')
                else:
                    collectionsByName[collname] = collection

        # Extract counts from management page
        logged_driver_get(self.driver, self.base_url+'/organize/en-US/transclude/manage-custom-list-modal/r1000')
        label = self.driver.title
        if not label:
            label = self.driver.current_url
        print(f"Extracting custom list counts from page {label}")
        collectionList = xpathByClass(self.driver,'//button','core-dropdown-list__item','')
        for coll in collectionList:
            collname = xpathByClass(coll,'.//span','core-list-cell__title','')[0].get_attribute("textContent")
            recipecount = re.sub(r' Recipes?','',xpathByClass(coll,'.//span','core-list-cell__subtitle','')[0].get_attribute("textContent"))
            if collname in collectionsByName:
                collectionsByName[collname].official_recipe_count = int(recipecount)
            else:
                print(f'Unexpected collection {collname} in recipe collection list')



# --------------- Static Scraping Functions ------------------

def xpathByClass(top,el,cls,ext):
    path = f"{el}[contains(concat(' ',normalize-space(@class),' '), ' {cls} ')]{ext}"
    lst = top.find_elements(By.XPATH,path)
    return lst


def parse_ingredients_with_lxml(section_html: str) -> list:
    """
    Parse ingredients section HTML with lxml (10x faster than Selenium).

    This function replicates getIngredient() logic but uses lxml for parsing,
    reducing ~500ms of Selenium overhead to ~10ms of Python parsing.

    Args:
        section_html: innerHTML of the ingredients section

    Returns:
        List of ingredient strings with proper formatting
    """
    from lxml import html as lxml_html

    # Parse HTML with lxml
    tree = lxml_html.fromstring(section_html)

    ingredient_texts = []

    # Find all h5 and li elements (same as XPath: .//*[self::h5 or self::li])
    for element in tree.xpath(".//*[self::h5 or self::li]"):
        if element.tag == 'h5':
            # Section header
            text = element.text_content().strip()
            ingredient_texts.append(f"\n{text}:\n")
            continue

        # Process <li> ingredient element
        ingred = ""

        # Check for simple ingredient format
        simple = element.cssselect('.recipe-ingredient--simple')
        if simple:
            ingredient_texts.append(simple[0].text_content().strip())
            continue

        # Extract amount
        amount_els = element.cssselect('.recipe-ingredient__amount')
        if amount_els:
            amnt = amount_els[0].text_content().replace('\n', ' ').strip()
            if amnt:
                ingred += amnt + " "

        # Extract ingredient name
        name_els = element.cssselect('.recipe-ingredient__name')
        if name_els:
            ingred += name_els[0].text_content().strip()

        # Extract description
        desc_els = element.cssselect('.recipe-ingredient__description')
        if desc_els:
            desc_text = desc_els[0].text_content().strip().replace('\n', ' ')
            ingred += re.sub(r', [(]', ' (', ", " + desc_text)

        # Extract alternatives
        alt_els = element.cssselect('.recipe-ingredient__alternative')
        for alt in alt_els:
            alt_text = alt.text_content().strip().replace('\n', ' ')
            ingred += f"\n>>>or {alt_text}"

        ingredient_texts.append(ingred)

    return ingredient_texts


def parse_directions_with_lxml(section_html: str) -> list:
    """
    Parse directions section HTML with lxml (faster than Selenium).

    Args:
        section_html: innerHTML of the directions section

    Returns:
        List of direction strings with proper formatting
    """
    from lxml import html as lxml_html

    # Parse HTML with lxml
    tree = lxml_html.fromstring(section_html)

    direction_texts = []

    # Find all h5 and li elements
    for element in tree.xpath(".//*[self::h5 or self::li]"):
        if element.tag == 'h5':
            # Section header
            text = element.text_content().strip()
            direction_texts.append(f"{text}:")
        else:
            # Direction text - collapse whitespace
            text = element.text_content()
            text = re.sub(r' +', ' ', text).replace('\n', '').strip()
            direction_texts.append(text)

    return direction_texts


def parse_collection_tiles_with_lxml(page_html: str, collection_type: str, base_url: str = 'https://cookidoo.thermomix.com') -> list:
    """
    Parse collection page HTML to extract recipe tiles (faster than Selenium).

    Args:
        page_html: Full page HTML
        collection_type: Type of collection ('created', 'saved', 'custom', 'bookmark')
        base_url: Base URL for converting relative URLs to absolute

    Returns:
        List of tuples: (recipe_id, recipe_name, recipe_url)
    """
    from lxml import html as lxml_html
    from urllib.parse import urljoin

    tree = lxml_html.fromstring(page_html)
    recipes = []

    # Find all core-tile elements
    tiles = tree.cssselect('core-tile')

    for tile in tiles:
        # Extract recipe ID
        if collection_type == 'created':
            recipe_id = tile.get('id')
        else:
            recipe_id = tile.get('data-recipe-id')

        if not recipe_id:
            continue

        # Extract recipe name
        name_elements = tile.cssselect('.core-tile__description-text')
        recipe_name = name_elements[0].text_content().strip() if name_elements else ''

        # Extract recipe URL (convert relative to absolute)
        link_elements = tile.cssselect('a')
        if link_elements:
            href = link_elements[0].get('href', '')
            # Convert relative URLs to absolute
            recipe_url = urljoin(base_url, href) if href else ''
        else:
            recipe_url = ''

        if recipe_id and recipe_name and recipe_url:
            recipes.append((recipe_id, recipe_name, recipe_url))

    return recipes


def getDevices(top, recipe, recipe_obj: Recipe):
    # Check devices and note recipes that are TM7-only or TM7 excluded
    deviceList = [li.text.strip() for li in top.find_elements(By.TAG_NAME,'recipe-device') if re.match(r"TM[567]",li.text.strip())]
    if len(deviceList) == 0:
        print('No device list found for '+recipe.title)
    elif len(deviceList) == 1 and deviceList[0] == 'TM7':
        recipe_obj.categories.append('TM7 Only')
        #print('Detected TM7-only recipe '+recipe.title)
    if not 'TM7' in deviceList:
        recipe_obj.categories.append('Not TM7')
        #print('Detected Not TM7 recipe '+recipe.title)



# ------------- Static Utility Functions --------------

def encode_image(self, image_path: Path) -> str:
    """Return base64 string of image contents."""
    return base64.b64encode(image_path.read_bytes()).decode("ascii")


def fixText(str):
    """Removes private use characters and other formatting corrections for Paprika 3"""
    puchars = {
        u'\ue001' : "knead",
        u'\ue002' : "stir",
        u'\ue003' : "reverse",
        u'\ue004' : "forward",
        u'\ue008' : "Varoma",
        u'\ue00B' : "Turbo",
        u'\ue00C' : "Sugar Stages",
        u'\ue00D' : "Rice Cooker",
        u'\ue011' : "Pre-clean",
        u'\ue014' : "Steam",
        u'\ue016' : "Kettle",
        u'\ue018' : "Slow Cook",
        u'\ue019' : "Warm Up",
        u'\ue01E' : "Blend",
        u'\ue026' : "High Heat",
        u'\ue02D' : "Sous Vide",
        u'\ue02E' : "Ferment",
        u'\ue031' : "Thicken",
        u'\ue032' : "Timer",
        u'\ue033' : "Egg Boiler",
        u'\ue036' : "Grating",
        u'\ue037' : "Slicing",
        u'\ue038' : "Peeler",
        u'\ue04c' : "Spiralize",
        u'\ue904' : "Spiralize",
        u'\ue937' : "Open Cooking",
    }
    for key, value in puchars.items():
        str = str.replace(key,value)
    str = str.replace(u'\u00a0',' ')
    str = re.sub(' +',' ',str)
    return str


def fixTime(str):
    """Modify time strings to match Paprika 3 conventions"""
    str = re.sub(r'([0-9]+) *h[a-z]*',r'\1 hr',str)
    str = re.sub(r'([0-9]+) *mi[a-z]*',r'\1 min',str)
    str = re.sub(r' *\n *',' ',str)
    return str


class CollectionProcessor:
    """Processes a single collection with its own browser instance."""

    def __init__(self, config: ScrapingConfiguration, browser_manager: ThreadSafeBrowserManager,
                 result_collector: ThreadSafeResultCollector, scraper_instance):
        self.config = config
        self.browser_manager = browser_manager
        self.result_collector = result_collector
        self.scraper = scraper_instance  # Access to scraper methods
        self.driver = None

    def __enter__(self):
        """Context manager entry - create browser instance."""
        self.driver = self.browser_manager.create_authenticated_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup browser instance."""
        if self.driver:
            self.browser_manager.close_driver(self.driver)

    def process_collection(self, collection: Collection) -> Collection:
        """Process a single collection - populate data and handle recipes."""
        try:
            _page_logger.log_timing("START collection", collection.title)

            # Navigate to collection page
            logged_driver_get(self.driver, collection.url)

            # Populate collection data using local driver
            collection = self.scraper.populateCollectionData(self.driver, collection, self.config)

            # Save collection text file
            filename = f'{collection.colltype} {collection.title}'
            ScraperSetup.save_text(
                self.config.output_dir,
                filename,
                collection.recipe_list_text,
                len(collection.all_recipes)
            )

            # Process recipes in parallel child threads if JSON export enabled
            if self.config.json_export and collection.json_recipes:
                collection = self.process_recipes_parallel(collection)

            # Update collection counter
            self.result_collector.increment_counters(collections=1)

            _page_logger.log_timing("COMPLETE collection", f"{collection.title} ({len(collection.json_recipes)} recipes)")

            return collection

        except Exception as e:
            error_msg = f"Collection processing error for {collection.title}: {e}"
            _page_logger.log_timing("ERROR collection", f"{collection.title} - {str(e)}")
            self.result_collector.add_error(error_msg)
            return collection

    def process_recipes_parallel(self, collection: Collection) -> Collection:
        """Process recipes in parallel child threads with memory management."""
        max_recipe_threads = self.config.max_recipe_threads

        with ThreadPoolExecutor(max_workers=max_recipe_threads) as recipe_executor:
            futures = []
            for recipe in collection.json_recipes:
                if self.result_collector.mark_recipe_for_processing(recipe.id):
                    future = recipe_executor.submit(self.process_single_recipe, recipe, collection.colltype)
                    futures.append(future)

            # Wait for all recipe processing to complete
            processed_recipes = []
            for future in as_completed(futures):
                try:
                    processed_recipe = future.result()
                    processed_recipes.append(processed_recipe)
                except Exception as e:
                    self.result_collector.add_error(f"Recipe processing error: {e}")

            # Clean up memory for processed recipes
            self.cleanup_recipe_memory(processed_recipes)

        return collection

    def cleanup_recipe_memory(self, recipes: List[Recipe]):
        """Clean up memory for recipes that have been JSON exported."""
        memory_cleared_count = 0
        total_memory_saved = 0

        for recipe in recipes:
            if self.result_collector.can_clear_memory(recipe.id):
                # Get memory usage before clearing (for statistics)
                memory_before = recipe.get_estimated_memory_usage()

                # Clear memory-heavy fields
                if recipe.clear_memory_heavy_fields():
                    self.result_collector.mark_recipe_memory_cleared(recipe.id)
                    memory_cleared_count += 1

                    # Calculate memory saved
                    memory_after = recipe.get_estimated_memory_usage()
                    total_memory_saved += (memory_before - memory_after)

        if memory_cleared_count > 0:
            print(f"Memory cleanup: cleared {memory_cleared_count} recipes, saved ~{total_memory_saved:,} bytes")

    def process_single_recipe(self, recipe: Recipe, collection_type: str) -> Recipe:
        """Process a single recipe with its own browser instance."""
        with RecipeProcessor(self.config, self.browser_manager, self.result_collector, self.scraper) as processor:
            return processor.process_recipe(recipe, collection_type)


class RecipeProcessor:
    """Processes a single recipe with its own browser instance."""

    def __init__(self, config: ScrapingConfiguration, browser_manager: ThreadSafeBrowserManager,
                 result_collector: ThreadSafeResultCollector, scraper_instance):
        self.config = config
        self.browser_manager = browser_manager
        self.result_collector = result_collector
        self.scraper = scraper_instance  # Access to scraper methods
        self.driver = None

    def __enter__(self):
        """Context manager entry - create browser instance."""
        self.driver = self.browser_manager.create_authenticated_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup browser instance."""
        if self.driver:
            self.browser_manager.close_driver(self.driver)

    def process_recipe(self, recipe: Recipe, collection_type: str) -> Recipe:
        """Process a single recipe completely."""
        try:
            _page_logger.log_timing("START recipe", recipe.title)

            # Navigate to recipe page and extract all data
            logged_driver_get(self.driver, recipe.url)
            recipe = self.scraper.populateRecipeData(self.driver, recipe, collection_type)
            recipe.mark_full_data_loaded()

            # Generate and save JSON
            recipe_json = self.scraper.recipeToJSON(recipe)

            if hasattr(self.config, 'json_dir'):
                json_dir = self.config.json_dir
            else:
                json_dir = self.scraper.args.json if hasattr(self.scraper, 'args') else 'json'

            ScraperSetup.save_json(
                self.config.output_dir,
                json_dir,
                recipe.id,
                recipe_json
            )

            # Mark that JSON has been exported (enables memory cleanup)
            recipe.mark_json_exported()
            self.result_collector.mark_recipe_json_exported(recipe.id)
            self.result_collector.increment_counters(recipes=1)

            _page_logger.log_timing("COMPLETE recipe", recipe.title)

            return recipe

        except Exception as e:
            error_msg = f"Recipe processing error for {recipe.title}: {e}"
            _page_logger.log_timing("ERROR recipe", f"{recipe.title} - {str(e)}")
            self.result_collector.add_error(error_msg)
            return recipe


class CookidooScraper:
    """Main Cookidoo scraper with multi-threaded collection and recipe processing."""

    def __init__(self, config: ScrapingConfiguration = None):
        """
        Initialize CookidooScraper with configuration.

        Args:
            config: Configuration to use (if None, creates default with command line overrides)
        """
        # Single initialization path: start with defaults, override with command line args
        if config is not None:
            self.config = config
        else:
            # Parse command line arguments
            args = parse_main_args()
            # Create configuration from args using the standard method
            self.config = ConfigurationManager.create_config_from_args(args)

        # Validate configuration
        validation_issues = ConfigurationManager.validate_configuration(self.config)
        if validation_issues:
            print("Configuration validation warnings:")
            for issue in validation_issues:
                print(f"  - {issue}")
            print("Continuing with current configuration...")
        else:
            print("Configuration validated successfully")

        # Initialize scraper for initial setup and collection discovery
        self.scraper = ScraperSetup(self.config)

        # Update config with scraper-discovered properties
        self.config.base_url = self.scraper.base_url
        self.config.valid_categories = self.scraper.validCategories

        # Get authentication cookies from main scraper
        self.cookies_data = self.scraper.driver.get_cookies()

        # Create thread managers
        self.browser_manager = ThreadSafeBrowserManager(self.config, self.cookies_data)
        self.result_collector = ThreadSafeResultCollector()



    def run(self):
        """Main execution method with parallel processing."""
        print("Starting multi-threaded collection processing...")
        logged_driver_get(self.scraper.driver, self.scraper.collections_page)
        print(f'Browser page title is {self.scraper.driver.title}')


        # Use single-threaded scraper for initial collection discovery
        # (This is complex coordination that's better done sequentially)
        collections = []
        collections.extend(self.scraper.getFixedCollections(self.scraper.driver))
        collections.extend(self.scraper.getCustomCollections(self.scraper.driver))
        collections.extend(self.scraper.getSavedCollections(self.scraper.driver))

        # Handle custom collection counts (single-threaded coordination)
        self.scraper._handle_custom_collection_counts(collections)

        # Process collections in parallel threads
        processed_collections = self.process_collections_parallel(collections)

        # Generate final outputs using single-threaded scraper
        self.generate_final_outputs(processed_collections)

        # Close main scraper
        self.scraper.close()

        # Print final statistics
        self.print_summary()

    def process_collections_parallel(self, collections: List[Collection]) -> List[Collection]:
        """Process collections in parallel threads."""
        processed = []

        # Filter collections to process
        collections_to_process = [
            coll for coll in collections
            if self.should_process_collection(coll)
        ]

        print(f"Processing {len(collections_to_process)} collections in parallel with {self.config.max_collection_threads} threads...")

        with ThreadPoolExecutor(max_workers=self.config.max_collection_threads) as collection_executor:
            futures = {}

            for collection in collections_to_process:
                future = collection_executor.submit(self.process_single_collection, collection)
                futures[future] = collection

            for future in as_completed(futures):
                try:
                    processed_collection = future.result()
                    processed.append(processed_collection)
                    print(f"Completed collection: {processed_collection.title}")
                except Exception as e:
                    collection = futures[future]
                    error_msg = f"Collection processing error for {collection.title}: {e}"
                    self.result_collector.add_error(error_msg)

        return collections  # Return all collections for master index generation

    def process_single_collection(self, collection: Collection) -> Collection:
        """Process a single collection in its own thread."""
        with CollectionProcessor(self.config, self.browser_manager, self.result_collector, self.scraper) as processor:
            return processor.process_collection(collection)

    def should_process_collection(self, collection: Collection) -> bool:
        """Determine if collection should be processed (same logic as original)."""
        # Replicate the original logic exactly:
        # (collection.colltype == 'saved' and self.config.saved_collections) or (self.config.pattern is None) or self.config.collection_pattern.search(collection.title) is not None

        # Condition 1: It's a saved collection AND --saved flag is set
        if collection.colltype == 'saved' and self.config.saved_collections:
            return True

        # Condition 2: No pattern specified (process all non-saved collections)
        if self.config.pattern is None:
            return True

        # Condition 3: Pattern matches collection title
        if self.config.collection_pattern is not None:
            return self.config.collection_pattern.search(collection.title) is not None

        return False

    def generate_final_outputs(self, collections: List[Collection]):
        """Generate master index and other final outputs."""
        # Use original scraper logic for master index
        index = "".join(["{}\t{}\t{}\n".format(coll.master_index_count,coll.colltype,coll.title)
            for coll in sorted(collections, key=lambda coll: (coll.colltype,coll.title))])
        ScraperSetup.save_text(self.scraper.output_dir, "Master Index", index, len(collections))

    def print_summary(self):
        """Print final processing summary with memory management statistics."""
        processed_collections, processed_recipes, error_count = self.result_collector.get_stats()
        memory_stats = self.result_collector.get_memory_stats()

        if processed_collections == 0 and processed_recipes == 0:
            print('** WARNING: You have no collections or recipes, or no collections or recipes matched the given pattern')
        else:
            print(f'Multi-threaded processing complete!')
            print(f'Processed {processed_recipes} recipes from {processed_collections} collections')

            # Print memory management statistics
            if memory_stats['total_recipes'] > 0:
                print(f"Memory management: {memory_stats['memory_cleared']} recipes cleared, "
                      f"{memory_stats['json_exported']} exported, "
                      f"{memory_stats['full_data']} still in memory")

                # Calculate memory efficiency
                if memory_stats['memory_cleared'] > 0:
                    efficiency = (memory_stats['memory_cleared'] / memory_stats['total_recipes']) * 100
                    print(f"Memory efficiency: {efficiency:.1f}% of recipes optimized")

            if error_count > 0:
                print(f'Encountered {error_count} errors during processing')


if  __name__ =='__main__':
    # Parse arguments first
    args = parse_main_args()

    print("Starting Cookidoo scraper...")
    scraper = CookidooScraper()

    scraper.run()
