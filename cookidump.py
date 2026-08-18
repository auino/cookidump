#!/usr/bin/python3

# cookidump
# Original GitHub project:
# https://github.com/auino/cookidump

import os
import io
import re
import time
import json
import pathlib
import argparse
import platform
from bs4 import BeautifulSoup
from selenium import webdriver
from urllib.parse import urlparse
from urllib.request import urlretrieve
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains

PAGELOAD_TO = 3
SCROLL_TO = 1
MAX_SCROLL_RETRIES = 5

def startBrowser(chrome_driver_path):
    chrome_options = Options()
    if "GOOGLE_CHROME_PATH" in os.environ:
        chrome_options.binary_location = os.getenv('GOOGLE_CHROME_PATH')
    chrome_service = Service(chrome_driver_path)
    driver = webdriver.Chrome(service=chrome_service, options=chrome_options)
    return driver

def listToFile(browser, baseDir):
    filename = '{}index.html'.format(baseDir)
    path = pathlib.Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    html = browser.execute_script("return document.documentElement.outerHTML")
    with io.open(filename, 'w', encoding='utf-8') as f: f.write(html)

def imgToFile(outputdir, recipeID, img_url):
    img_path = '{}images/{}.jpg'.format(outputdir, recipeID)
    path = pathlib.Path(img_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    urlretrieve(img_url, img_path)
    return '../images/{}.jpg'.format(recipeID)

def recipeToFile(browser, filename):
    path = pathlib.Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    html = browser.page_source
    with io.open(filename, 'w', encoding='utf-8') as f: f.write(html)

def recipeToJSON(browser, recipeID):
    html = browser.page_source
    soup = BeautifulSoup(html, 'html.parser')

    recipe = {}
    recipe['id'] = recipeID

    # First try to extract data from JSON-LD structured data
    json_ld_data = None
    try:
        json_ld_script = soup.find('script', type='application/ld+json')
        if json_ld_script:
            json_ld_data = json.loads(json_ld_script.string)
    except:
        pass

    # Language
    try:
        recipe['language'] = soup.select_one('html').attrs['lang']
    except:
        recipe['language'] = 'unknown'

    # Title - try JSON-LD first, then fallback to HTML parsing
    if json_ld_data and 'name' in json_ld_data:
        recipe['title'] = json_ld_data['name']
    else:
        title_selectors = [
            ".recipe-card__title",
            "h1[class*='title']",
            "h1",
            "[class*='recipe-title']",
            "[class*='recipe__title']"
        ]
        recipe['title'] = 'Unknown Title'
        for selector in title_selectors:
            try:
                title_elem = soup.select_one(selector)
                if title_elem and title_elem.text.strip():
                    recipe['title'] = title_elem.text.strip()
                    break
            except:
                continue

    # Rating count
    try:
        recipe['rating_count'] = re.sub(r'\D', '', soup.select_one(".core-rating__label").text, flags=re.IGNORECASE)
    except:
        recipe['rating_count'] = '0'

    # Rating score
    try:
        recipe['rating_score'] = soup.select_one(".core-rating__counter").text
    except:
        recipe['rating_score'] = '0'

    # TM versions
    try:
        recipe['tm-versions'] = [v.text.replace('\n','').strip().lower() for v in soup.select(".recipe-card__tm-version core-badge")]
    except:
        recipe['tm-versions'] = []

    # Features
    try:
        recipe.update({ l.text : l.next_sibling.strip() for l in soup.select("core-feature-icons label span") })
    except:
        pass

    # Ingredients - try JSON-LD first, then fallback to HTML parsing
    if json_ld_data and 'recipeIngredient' in json_ld_data:
        recipe['ingredients'] = json_ld_data['recipeIngredient']
    else:
        ingredients_selectors = [
            "#ingredients li",
            "[class*='ingredient'] li",
            "[class*='ingredients'] li",
            "ul[class*='ingredient'] li"
        ]
        recipe['ingredients'] = []
        for selector in ingredients_selectors:
            try:
                ingredients = [re.sub(' +', ' ', li.text).replace('\n','').strip() for li in soup.select(selector)]
                if ingredients:
                    recipe['ingredients'] = ingredients
                    break
            except:
                continue

    # Nutritions - try JSON-LD first, then fallback to HTML parsing
    recipe['nutritions'] = {}
    if json_ld_data and 'nutrition' in json_ld_data:
        nutrition = json_ld_data['nutrition']
        if isinstance(nutrition, dict):
            recipe['nutritions'] = {k.replace('Content', ''): v for k, v in nutrition.items() if k != '@type'}
    else:
        nutrition_containers = [
            ".nutritions dl",
            "[class*='nutrition'] dl",
            "[class*='nutritions'] dl"
        ]
        for container_selector in nutrition_containers:
            try:
                containers = soup.select(container_selector)
                if containers:
                    for item in list(zip(containers[0].find_all("dt"), containers[0].find_all("dd"))):
                        dt, dl = item
                        try:
                            dt_text = dt.get_text().replace('\n','').strip().lower() if dt.string else dt.get_text().replace('\n','').strip().lower()
                            dl_text = dl.get_text().replace('\n','').strip().lower() if dl.string else dl.get_text().replace('\n','').strip().lower()
                            recipe['nutritions'].update({ dt_text: re.sub(r'\s{2,}', ' ', dl_text) })
                        except:
                            continue
                    if recipe['nutritions']:
                        break
            except:
                continue

    # Steps - try JSON-LD first, then fallback to HTML parsing
    if json_ld_data and 'recipeInstructions' in json_ld_data:
        instructions = json_ld_data['recipeInstructions']
        recipe['steps'] = []
        for step in instructions:
            if isinstance(step, dict) and 'text' in step:
                recipe['steps'].append(step['text'])
            elif isinstance(step, str):
                recipe['steps'].append(step)
    else:
        steps_selectors = [
            "#preparation-steps li",
            "[class*='preparation'] li",
            "[class*='step'] li",
            "[class*='instruction'] li",
            "ol[class*='step'] li"
        ]
        recipe['steps'] = []
        for selector in steps_selectors:
            try:
                steps = [re.sub(' +', ' ', li.text).replace('\n','').strip() for li in soup.select(selector)]
                if steps:
                    recipe['steps'] = steps
                    break
            except:
                continue

    # Tags - try JSON-LD first, then fallback to HTML parsing
    if json_ld_data and 'keywords' in json_ld_data:
        tags_str = json_ld_data['keywords']
        if isinstance(tags_str, str):
            recipe['tags'] = [tag.strip().lower() for tag in tags_str.split(',')]
        elif isinstance(tags_str, list):
            recipe['tags'] = [str(tag).strip().lower() for tag in tags_str]
        else:
            recipe['tags'] = []
    else:
        tags_selectors = [
            ".core-tags-wrapper__tags-container a",
            "[class*='tag'] a",
            "[class*='tags'] a"
        ]
        recipe['tags'] = []
        for selector in tags_selectors:
            try:
                tags = [a.text.replace('#','').replace('\n','').strip().lower() for a in soup.select(selector)]
                if tags:
                    recipe['tags'] = tags
                    break
            except:
                continue

    return recipe

def run(webdriverfile, outputdir, separate_json):
    print('[CD] Welcome to cookidump, starting things off...')
    if outputdir[-1:][0] != '/': outputdir += '/'
    locale = str(input('[CD] Complete the website domain: https://cookidoo.'))
    baseURL = 'https://cookidoo.{}/'.format(locale)
    brw = startBrowser(webdriverfile)
    brw.get(baseURL)
    time.sleep(PAGELOAD_TO)
    input('[CD] Please login to your account and then enter y to continue: ')
    rbURL = 'https://cookidoo.{}/search/'.format(locale)
    brw.get(rbURL)
    time.sleep(PAGELOAD_TO)
    input('[CD] Set your filters, if any, and then enter y to continue: ')
    custom_output_dir = input("[CD] enter the directory name to store the results (ex. vegetarian): ")
    if custom_output_dir: outputdir += '{}/'.format(custom_output_dir)
    print('[CD] Proceeding with scraping')
    brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element(By.TAG_NAME, 'core-user-profile'))
    try: brw.find_element(By.CLASS_NAME, 'accept-cookie-container').click()
    except: pass
    try:
        methods = [
            lambda: brw.find_element(By.CLASS_NAME, 'items-start').text,
            lambda: brw.find_element(By.CSS_SELECTOR, '[class*="count"]').text,
            lambda: brw.find_element(By.CSS_SELECTOR, '[class*="total"]').text,
            lambda: brw.find_element(By.CSS_SELECTOR, '[class*="results"]').text
        ]

        elementsToBeFound = 0
        for method in methods:
            try:
                text = method()
                numbers = re.findall(r'\d+', text)
                if numbers:
                    elementsToBeFound = int(numbers[-1])
                    break
            except:
                continue

        if elementsToBeFound == 0:
            print('[CD] Could not determine recipe count, using manual scrolling')
            elementsToBeFound = 999999
        else:
            print('[CD] Found {} recipes to scrape'.format(elementsToBeFound))
    except Exception as e:
        print('[CD] Error determining recipe count: {}, using manual scrolling'.format(str(e)))
        elementsToBeFound = 999999
    previousElements = 0
    count = 0
    while True:
        currentElements = len(brw.find_elements(By.CLASS_NAME, 'link--alt'))
        if currentElements >= elementsToBeFound: break
        brw.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_TO)
        try:
            brw.find_element(By.XPATH, "//button[@data-cy='load-more-button']").click()
            time.sleep(PAGELOAD_TO)
        except: pass
        print('Scrolling [{}/{}]'.format(currentElements, elementsToBeFound if elementsToBeFound < 999999 else 'unknown'))
        count = count + 1 if previousElements == currentElements else 0
        if count >= MAX_SCROLL_RETRIES: break
        previousElements = currentElements

    print('Scrolling [{}/{}]'.format(currentElements, elementsToBeFound))

    els = brw.find_elements(By.CLASS_NAME, 'link--alt')
    recipesURLs = []
    for el in els:
        recipeURL = el.get_attribute('href')
        recipesURLs.append(recipeURL)
        recipeID = recipeURL.split('/')[-1:][0]
        brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", el, 'href', './recipes/{}.html'.format(recipeID))

    try: brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element(By.TAG_NAME, 'core-search-bar'))
    except: pass

    for s in brw.find_elements(By.TAG_NAME, 'script'):
        try: brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)
        except: pass

    listToFile(brw, outputdir)
    recipesURLs = [l for l in recipesURLs if 'recipe' in l]
    print("Getting all recipes...")
    c = 0
    recipeData = []
    for recipeURL in recipesURLs:
        try:
            u = str(urlparse(recipeURL).path)
            if u[0] == '/': u = '.'+u
            recipeID = u.split('/')[-1:][0]
            brw.get(recipeURL)
            time.sleep(PAGELOAD_TO)
            try: brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element(By.TAG_NAME, 'base'))
            except: pass
            brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element(By.TAG_NAME, 'core-user-profile'))
            brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", brw.find_element(By.CLASS_NAME, 'page-header__home'), 'href', '../../index.html')

            try:
                img_url = brw.find_element(By.ID, 'recipe-card__image-loader').find_element(By.TAG_NAME, 'img').get_attribute('src')
            except:
                try:
                    img_url = brw.find_element(By.CLASS_NAME, 'recipe-card__image').find_element(By.TAG_NAME, 'img').get_attribute('src')
                except:
                    try:
                        img_url = brw.find_element(By.CLASS_NAME, 'core-tile__image').get_attribute('src')
                    except:
                        print('[CD] Warning: Could not find image for recipe {}'.format(recipeID))
                        img_url = None

            if img_url:
                local_img_path = imgToFile(outputdir, recipeID, img_url)
                try:
                    brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", brw.find_element(By.CLASS_NAME, 'core-tile__image'), 'srcset', '')
                    brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", brw.find_element(By.CLASS_NAME, 'core-tile__image'), 'src', local_img_path)
                except:
                    print('[CD] Warning: Could not update image links for recipe {}'.format(recipeID))

            recipeToFile(brw, '{}recipes/{}.html'.format(outputdir, recipeID))
            recipe = recipeToJSON(brw, recipeID)
            if separate_json:
                print('[CD] Writing recipe to JSON file')
                with open('{}recipes/{}.json'.format(outputdir, recipeID), 'w') as outfile: json.dump(recipe, outfile)
            else:
                recipeData.append(recipe)
            c += 1
            if c % 10 == 0: print('Dumped recipes: {}/{}'.format(c, len(recipesURLs)))
        except Exception as e:
            print('[CD] Error processing recipe {}: {}'.format(recipeURL, str(e)))

    if not separate_json:
        print('[CD] Writing recipes to JSON file')
        with open('{}data.json'.format(outputdir), 'w') as outfile: json.dump(recipeData, outfile)

    logoutURL = 'https://cookidoo.{}/profile/logout'.format(locale)
    brw.get(logoutURL)
    time.sleep(PAGELOAD_TO)
    print('[CD] Closing session\n[CD] Goodbye!')
    brw.close()

if  __name__ =='__main__':
    parser = argparse.ArgumentParser(description='Dump Cookidoo recipes from a valid account')
    parser.add_argument('webdriverfile', type=str, help='the path to the Chrome WebDriver file')
    parser.add_argument('outputdir', type=str, help='the output directory')
    parser.add_argument('-s', '--separate-json', action='store_true', help='Create a separate JSON file for each recipe; otherwise, a single data file will be generated')
    args = parser.parse_args()
    run(args.webdriverfile, args.outputdir, args.separate_json)
