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
from selenium import webdriver
from urllib.parse import urlparse
from urllib.request import urlretrieve
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup

PAGELOAD_TO = 3
SCROLL_TO = 1
MAX_SCROLL_RETRIES = 5

def startBrowser(chrome_driver_path):
    """Starts browser with predefined parameters"""
    chrome_options = Options()
    #chrome_options.add_argument('--headless')
    driver = webdriver.Chrome(executable_path=chrome_driver_path, options=chrome_options)
    return driver

def listToFile(browser, baseDir):
    """Gets html from search list and saves in html file"""
    filename = '{}index.html'.format(baseDir)
    # creating directories, if needed
    path = pathlib.Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    # getting web page source
    #html = browser.page_source
    html = browser.execute_script("return document.documentElement.outerHTML") 
    # saving the page
    with io.open(filename, 'w', encoding='utf-8') as f: f.write(html)

def imgToFile(outputdir, recipeID, img_url):
    img_path = '{}images/{}.jpg'.format(outputdir, recipeID)
    path = pathlib.Path(img_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    urlretrieve(img_url, img_path)
    return '../images/{}.jpg'.format(recipeID)

def recipeToFile(browser, filename):
    """Gets html of the recipe and saves in html file"""
    # creating directories, if needed
    path = pathlib.Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    # getting web page source
    html = browser.page_source
    # saving the page
    with io.open(filename, 'w', encoding='utf-8') as f: f.write(html)

def recipeToJSON(browser, recipeID):
    html = browser.page_source
    soup = BeautifulSoup(html, 'html.parser')

    recipe = {}
    recipe['id'] = recipeID
    recipe['language'] = soup.select_one('html').attrs['lang']
    recipe['title'] = soup.select_one(".recipe-card__title").text
    recipe['rating_count'] = re.sub(r'\D', '', soup.select_one(".core-rating__label").text, flags=re.IGNORECASE)
    recipe['rating_score'] = soup.select_one(".core-rating__counter").text
    recipe['tm-versions'] = [v.text.replace('\n','').strip().lower() for v in soup.select(".recipe-card__tm-version core-badge")]
    recipe.update({ l.text : l.next_sibling.strip() for l in soup.select("core-feature-icons label span") })
    recipe['ingredients'] = [re.sub(' +', ' ', li.text).replace('\n','').strip() for li in soup.select("#ingredients li")]
    recipe['nutritions'] = {}
    for item in list(zip(soup.select(".nutritions dl")[0].find_all("dt"), soup.select(".nutritions dl")[0].find_all("dd"))):
        dt, dl = item
        recipe['nutritions'].update({ dt.string.replace('\n','').strip().lower(): re.sub(r'\s{2,}', ' ', dl.string.replace('\n','').strip().lower()) })
    recipe['steps'] = [re.sub(' +', ' ', li.text).replace('\n','').strip() for li in soup.select("#preparation-steps li")]
    recipe['tags'] = [a.text.replace('#','').replace('\n','').strip().lower() for a in soup.select(".core-tags-wrapper__tags-container a")]

    return recipe

def run(webdriverfile, outputdir, separate_json):
    """Scraps all recipes and stores them in html"""
    print('[CD] Welcome to cookidump, starting things off...')
    # fixing the outputdir parameter, if needed
    if outputdir[-1:][0] != '/': outputdir += '/'

    locale = str(input('[CD] Complete the website domain: https://cookidoo.'))
    baseURL = 'https://cookidoo.{}/'.format(locale)

    brw = startBrowser(webdriverfile)

    # opening the home page
    brw.get(baseURL)
    time.sleep(PAGELOAD_TO)

    reply = input('[CD] Please login to your account and then enter y to continue: ')
    
    base_outputdir=outputdir

    while True:
        # recipes base url
        rbURL = 'https://cookidoo.{}/search/'.format(locale)

        brw.get(rbURL)
        time.sleep(PAGELOAD_TO)

        # possible filters done here
        reply = input('[CD] Set your filters, if any, and then enter y to continue: ')
        
        outputdir = base_outputdir
        custom_output_dir = input("[CD] enter the directory name to store the results (ex. vegeratian): ")
        if custom_output_dir : outputdir += '{}/'.format(custom_output_dir)

        print('[CD] Proceeding with scraping')

        # clicking on cookie accept
        try: brw.find_element_by_class_name('accept-cookie-container').click()
        except: pass

        # showing all recipes
        elementsToBeFound = int(brw.find_element_by_class_name('search-results-count__hits').get_attribute('innerHTML'))
        previousElements = 0
        count=0
        while True:
            # checking if ended or not
            currentElements = len(brw.find_elements_by_class_name('core-tile--expanded'))
            if currentElements >= elementsToBeFound: break
            # scrolling to the end
            brw.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_TO)
            # clicking on the "load more recipes" button
            try:
                brw.find_element_by_id('load-more-page').click()
                time.sleep(PAGELOAD_TO)
            except: pass
            print('Scrolling [{}/{}]'.format(currentElements, elementsToBeFound))
            # checking if I can't load more elements
            count = count + 1 if previousElements == currentElements else 0
            if count >= MAX_SCROLL_RETRIES: break
            previousElements = currentElements
        
        print('Scrolling [{}/{}]'.format(currentElements, elementsToBeFound))

        # Cleanup
        for s in brw.find_elements_by_tag_name('script'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_class_name('page-header'))
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_class_name('l-content'))
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_class_name('keyboard-container'))
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('filter-button'))
        for s in brw.find_elements_by_tag_name('sort-by'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('filter-modal'))
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-toast'))
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('search-algolia'))
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('search-infinite-scroll'))
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-footer'))
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-tos-privacy-update'))
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-feedback')) 
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_id('onetrust-consent-sdk'))
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_id('onetrust-style'))  
        for s in brw.find_elements_by_tag_name('core-context-menu'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)
        for s in brw.find_elements_by_tag_name('core-error-page'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)
        for s in brw.find_elements_by_tag_name('noscript'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)

        for s in brw.find_elements_by_tag_name('img'):
            brw.execute_script("arguments[0].removeAttribute(arguments[1]);", s, 'srcset')
            brw.execute_script("arguments[0].removeAttribute(arguments[1]);", s, 'sizes')
            brw.execute_script("arguments[0].setAttribute(arguments[1],arguments[2]);", s, 'style','max-width:100%;')
        brw.execute_script('var element=document.querySelector("link[rel=\'icon\']");element.parentNode.removeChild(element);')
        brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('base'))

        brw.execute_script('var element=document.getElementsByTagName("link")[2];element.parentNode.removeChild(element);')
        brw.execute_script('var element=document.getElementsByTagName("link")[1];element.parentNode.removeChild(element);')
        brw.execute_script('var element=document.getElementsByTagName("link")[0];element.parentNode.removeChild(element);')

        #local css - DISABLED
        #brw.execute_script('var element=document.getElementsByTagName("link")[0];element.setAttribute(arguments[0], arguments[1]);','href','css/pl-core-20.36.0.css')
        #brw.execute_script('var element=document.getElementsByTagName("link")[1];element.setAttribute(arguments[0], arguments[1]);','href','css/styles.css')   

        # saving all recipes urls
        els = brw.find_elements_by_class_name('link--alt')
        recipesURLs = []
        for el in els:
            recipeURL = el.get_attribute('href')
            recipesURLs.append(recipeURL)
            recipeID = recipeURL.split('/')[-1:][0]
            brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", el, 'href', './recipes/{}.html'.format(recipeID))
            brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", el.find_element_by_tag_name('img'), 'src','images/{}.jpg'.format(recipeID))
            
        # saving the list to file
        listToFile(brw, outputdir)

        # filter recipe Url list because it contains terms-of-use, privacy, disclaimer links too
        recipesURLs = [l for l in recipesURLs if 'recipe' in l]

        # getting all recipes
        print("Getting all recipes...")
        c = 0
        recipeData = []
        for recipeURL in recipesURLs:
            try:
                # building urls
                u = str(urlparse(recipeURL).path)
                if u[0] == '/': u = '.'+u
                recipeID = u.split('/')[-1:][0]
                # opening recipe url
                brw.get(recipeURL)
                #Wait for page to load
                WebDriverWait(brw, PAGELOAD_TO).until(lambda driver: brw.execute_script('return document.readyState') == 'complete')
                # cleanup
                for s in brw.find_elements_by_tag_name('script'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)
                for s in brw.find_elements_by_tag_name('recipe-banner'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)
                for s in brw.find_elements_by_tag_name('core-modal'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)
                for s in brw.find_elements_by_tag_name('core-tooltip'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-toast'))
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-transclude'))
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-tos-privacy-update'))
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-feedback')) 
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-lazy-loading')) 
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-footer'))
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('recipe-cr-promo-banner'))    
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('recipe-scrollspy'))
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_class_name('page-header'))
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_class_name('recipe-card__btn-line'))
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_id('alternative-recipes'))
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_id('nutritions-mobile'))
                try: brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_id('in-collections'))
                except: pass
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_id('core-share'))
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_id('onetrust-style'))
                brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_id('onetrust-consent-sdk'))

                for s in brw.find_elements_by_class_name('core-action-list__item'): brw.execute_script("arguments[0].removeAttribute('href');", s)
                for s in brw.find_elements_by_class_name('core-badge--high'): brw.execute_script("arguments[0].removeAttribute('href');", s)   
                for s in brw.find_elements_by_tag_name('core-fetch-modal'): brw.execute_script("arguments[0].removeAttribute('href');", s)     

                brw.execute_script("arguments[0].removeAttribute(arguments[1]);", brw.find_element_by_tag_name('img'), 'srcset')
                brw.execute_script("arguments[0].removeAttribute(arguments[1]);", brw.find_element_by_tag_name('img'), 'sizes')
                brw.execute_script("arguments[0].setAttribute(arguments[1],arguments[2]);", brw.find_element_by_tag_name('img'), 'style','max-width:100%;')

                brw.execute_script('document.getElementsByClassName("l-header-offset-small")[0].classList.remove("l-header-offset-small");')   
                brw.execute_script('var element=document.querySelector("link[rel=\'icon\']");element.parentNode.removeChild(element);')

                #local css - DISABLED
                #brw.execute_script('var element=document.getElementsByTagName("link")[0];element.setAttribute(arguments[0], arguments[1]);','href','../css/pl-core-20.36.0.css')
                #brw.execute_script('var element=document.getElementsByTagName("link")[1];element.setAttribute(arguments[0], arguments[1]);','href','../css/bundle.css')
                #brw.execute_script('var element=document.getElementsByTagName("link")[2];element.parentNode.removeChild(element);')


                # saving recipe image
                img_url = brw.find_element_by_tag_name('img').get_attribute('src')
                local_img_path = imgToFile(outputdir, recipeID, img_url)

                # change the image url to local
                brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", brw.find_element_by_tag_name('img') , 'src', local_img_path)
                
                # saving the file
                recipeToFile(brw, '{}recipes/{}.html'.format(outputdir, recipeID))

                # extracting JSON info
                recipe = recipeToJSON(brw, recipeID)

                # saving JSON file, if needed
                if separate_json:
                    print('[CD] Writing recipe to JSON file')
                    with open('{}recipes/{}.json'.format(outputdir, recipeID), 'w') as outfile: json.dump(recipe, outfile)
                else:
                    recipeData.append(recipe)

                # printing information
                c += 1
                if c % 10 == 0: print('Dumped recipes: {}/{}'.format(c, len(recipesURLs)))
            except: pass

        # save JSON file, if needed
        if not separate_json:
            print('[CD] Writing recipes to JSON file')
            with open('{}data.json'.format(outputdir), 'w') as outfile: json.dump(recipeData, outfile)
            
        reply = input('[CD] Enter x to exit, y for more: ')
        if reply == 'x' : break

    # logging out
    logoutURL = 'https://cookidoo.{}/profile/logout'.format(locale)
    brw.get(logoutURL)
    time.sleep(PAGELOAD_TO)
    
    # closing session
    print('[CD] Closing session\n[CD] Goodbye!')
    brw.close()

if  __name__ =='__main__':
    parser = argparse.ArgumentParser(description='Dump Cookidoo recipes from a valid account')
    parser.add_argument('webdriverfile', type=str, help='the path to the Chrome WebDriver file')
    parser.add_argument('outputdir', type=str, help='the output directory')
    parser.add_argument('-s', '--separate-json', action='store_true', help='Create a separate JSON file for each recipe; otherwise, a single data file will be generated')
    args = parser.parse_args()
    run(args.webdriverfile, args.outputdir, args.separate_json)
