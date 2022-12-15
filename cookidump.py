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
from bs4 import BeautifulSoup

PAGELOAD_TO = 3
SCROLL_TO = 1
MAX_SCROLL_RETRIES = 5

def startBrowser(chrome_driver_path):
	"""Starts browser with predefined parameters"""
	chrome_options = Options()
	if "GOOGLE_CHROME_PATH" in os.environ:
		chrome_options.binary_location = os.getenv('GOOGLE_CHROME_PATH')
	#chrome_options.add_argument('--headless')
	driver = webdriver.Chrome(executable_path=chrome_driver_path, options=chrome_options)
	return driver

def listToFile(browser, baseDir, filename = 'index'):
	"""Gets html from search list and saves in html file"""
	filename = '{}'.format(baseDir) + filename + '.html'
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

	custom_output_dir = input("[CD] enter the directory name to store the results (ex. vegeratian): ")
	if custom_output_dir : outputdir += '{}/'.format(custom_output_dir)

	brw = startBrowser(webdriverfile)
	brw.set_window_size(750,1250)

	# opening the home page
	brw.get(baseURL)
	time.sleep(PAGELOAD_TO)

	reply = input('[CD] Please login to your account and then enter y to continue: ')

	# recipes base url
	rbURL = 'https://cookidoo.{}/search/'.format(locale)

	print('[CD] Counting filters')
	# count filters
	brw.get(rbURL)
	time.sleep(PAGELOAD_TO)

	# open filter menue
	brw.find_element_by_class_name('filter-button').click()
	time.sleep(1)
	brw.find_element_by_class_name('multi-select__label.multi-select__label--collapsed').click()
	time.sleep(1)

	filtercounter = []
	for i in range(99):
		try:
			label = '//label[@for="category-VrkNavCategory-RPF-' + str(i).rjust(3, '0') + '"]'
			# print(label)
			if len(brw.find_elements_by_xpath(label)) > 0:
				filtercounter.append(label)
		except:
			pass

	subfiltercounter = []
	subfiltercounter.append('//label[@for="easy"]')
	subfiltercounter.append('//label[@for="medium"]')
	subfiltercounter.append('//label[@for="advanced"]')
	print('[CD] Found ' + str(len(filtercounter)*len(subfiltercounter)) + ' filters')

	print('[CD] Proceeding with scraping')
	recipesURLs = []
	counter = 0
	for filter in filtercounter:
		for subfilter in subfiltercounter:
			counter += 1
			print('[CD] Stored URLS: ' + str(len(recipesURLs)))
			print('[CD] Filter [' + str(counter) + "/" + str(len(filtercounter)*len(subfiltercounter)) + "]")
			brw.get(rbURL)
			time.sleep(PAGELOAD_TO)

			# open filter menue
			brw.find_element_by_class_name('filter-button').click()
			time.sleep(1)
			brw.find_element_by_class_name('multi-select__label.multi-select__label--collapsed').click()
			time.sleep(1)

			# chose a filter
			scrollcounter = 100
			while True:
				try:
					brw.find_element_by_xpath(filter).click()
					break;
				except: 
					brw.execute_script("window.scrollTo(0, " + str(scrollcounter) + ");")
					scrollcounter += 100
			time.sleep(1)
			scrollcounter = 100
			while True:
				try:
					brw.find_element_by_xpath(subfilter).click()
					break;
				except: 
					brw.execute_script("window.scrollTo(0, " + str(scrollcounter) + ");")
					scrollcounter += 100
			time.sleep(1)
			brw.find_element_by_class_name('core-modal__submit.button--primary').click()
			time.sleep(1)
			

			# removing the base href header
			try:
				brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('base'))
			except: pass
			# removing the name
			try:
				brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-transclude'))
			except: pass
			# clicking on cookie accept
			try: brw.find_element_by_class_name('accept-cookie-container').click()
			except: pass

			# showing all recipes
			try:
				elementsToBeFound = int(brw.find_element_by_class_name('search-results-count__hits').get_attribute('innerHTML'))
			except:
				elementsToBeFound = 0
			previousElements = 0
			while True:
				# checking if ended or not
				currentElements = len(brw.find_elements_by_class_name('link--alt'))
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

			# saving all recipes urls
			els = brw.find_elements_by_class_name('link--alt')
			# recipesURLs = []
			for el in els:
				recipeURL = el.get_attribute('href')
				if not recipeURL in recipesURLs:
					recipesURLs.append(recipeURL)
				recipeID = recipeURL.split('/')[-1:][0]
				brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", el, 'href', './recipes/{}.html'.format(recipeID))

			# removing search bar
			brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('search-bar'))

			# removing scripts
			for s in brw.find_elements_by_tag_name('script'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)

			# saving the list to file
			listToFile(brw, outputdir, str(counter))

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
			time.sleep(PAGELOAD_TO)
			# removing the base href header
			try: brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('base'))
			except: pass
			# removing the name
			brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-transclude'))
			# changing the top url
			brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", brw.find_element_by_class_name('page-header__home'), 'href', '../../index.html')
			
			# saving recipe image
			img_url = brw.find_element_by_id('recipe-card__image-loader').find_element_by_tag_name('img').get_attribute('src')
			local_img_path = imgToFile(outputdir, recipeID, img_url)

			# change the image url to local
			brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", brw.find_element_by_class_name('core-tile__image'), 'srcset', '')
			brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", brw.find_element_by_class_name('core-tile__image'), 'src', local_img_path)
			
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
