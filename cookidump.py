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
	#chrome_options.add_argument('--headless')
	driver = webdriver.Chrome(executable_path=chrome_driver_path, options=chrome_options)
	return driver

def listToFile(browser, baseDir):
	"""Gets html from search list and saves in html file"""
	filename = baseDir+'index.html'
	# creating directories, if needed
	path = pathlib.Path(filename)
	path.parent.mkdir(parents=True, exist_ok=True)
	# getting web page source
	#html = browser.page_source
	html = browser.execute_script("return document.documentElement.outerHTML") 
	# saving the page
	with io.open(filename, 'w', encoding='utf-8') as f: f.write(html)

def imgToFile(outputdir, recipeID, img_url):
	img_path = outputdir+'images/'+recipeID+'.jpg'
	path = pathlib.Path(img_path)
	path.parent.mkdir(parents=True, exist_ok=True)
	urlretrieve(img_url, img_path)
	return '../images/'+recipeID+'.jpg'

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
	recipe['title'] = soup.select_one(".recipe-card__title").text
	recipe.update({ l.text : l.next_sibling.strip() for l in soup.select("core-feature-icons label span") })
	recipe['ingredients'] = [re.sub(' +', ' ', li.text).replace('\n','').strip() for li in soup.select("#ingredients li")]
	recipe['steps'] = [re.sub(' +', ' ', li.text).replace('\n','').strip() for li in soup.select("#preparation-steps li")]

	return recipe

def run(webdriverfile, outputdir, separateJson):
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

	# recipes base url
	rbURL = 'https://cookidoo.'+str(locale)+'/search/'

	brw.get(rbURL)
	time.sleep(PAGELOAD_TO)

	# possible filters done here
	reply = input('[CD] Set your filters, if any, and then enter y to continue: ')

	custom_output_dir = input("[CD] enter the directory name to store the results (ex. vegeratian ):")
	if custom_output_dir : outputdir = outputdir + custom_output_dir+'/'


	print('[CD] Proceeding with scraping')

	# removing the base href header
	brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('base'))

	# removing the name
	brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('core-transclude'))

	# clicking on cookie accept
	try: brw.find_element_by_class_name('accept-cookie-container').click()
	except: pass

	# showing all recipes
	elementsToBeFound = int(brw.find_element_by_class_name('search-results-count__hits').get_attribute('innerHTML'))
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
		print("Scrolling ["+str(currentElements)+"/"+str(elementsToBeFound)+"]")
		# checking if I can't load more elements
		count = count + 1 if previousElements == currentElements else 0
		if count >= MAX_SCROLL_RETRIES: break
		previousElements = currentElements

	print("Scrolling ["+str(currentElements)+"/"+str(elementsToBeFound)+"]")

	# saving all recipes urls
	els = brw.find_elements_by_class_name('link--alt')
	recipesURLs = []
	for el in els:
		recipeURL = el.get_attribute('href')
		recipesURLs.append(recipeURL)
		recipeID = recipeURL.split('/')[-1:][0]
		brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", el, 'href', './recipes/'+recipeID+'.html')

	# removing search bar
	brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", brw.find_element_by_tag_name('search-bar'))

	# removing scripts
	for s in brw.find_elements_by_tag_name('script'): brw.execute_script("var element = arguments[0];element.parentNode.removeChild(element);", s)

	# saving the list to file
	listToFile(brw, outputdir)

	# filter recipe Url list because it contains terms-of-use, privacy, disclaimer links too
	recipesURLs = [l for l in recipesURLs if 'recipe' in l]

	# getting all recipes
	print("Getting all recipes...")
	c = 0
	recipeData = []
	for recipeURL in recipesURLs:
		# try:
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
			
			# saving image for recipe
			img_url = brw.find_element_by_class_name('core-tile__image').get_attribute('src')
			local_img_path = imgToFile(outputdir, recipeID, img_url)

			# change the image url to local
			brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", brw.find_element_by_class_name('core-tile__image'), 'srcset', '')
			brw.execute_script("arguments[0].setAttribute(arguments[1], arguments[2]);", brw.find_element_by_class_name('core-tile__image'), 'src', local_img_path)
			
			# saving the file
			recipeToFile(brw, outputdir+'recipes/'+recipeID+'.html')

			# extracting JSON info
			recipe = recipeToJSON(brw, recipeID)

			if separateJson:
				# save json file
				print("Writing recipe to JSON file")
				with open(outputdir+'recipes/'+recipeID+'.json', 'w') as outfile:
					json.dump(recipe, outfile)
			else:
				recipeData.append(recipe)
			
			# printing information
			c += 1
			if c % 10 == 0: print("Dumped recipes: "+str(c)+"/"+str(len(recipesURLs)))
		# except: pass

	if not separateJson:
		# save json file
		print("Writing recipes to JSON file")
		with open(outputdir+'data.json', 'w') as outfile:
			json.dump(recipeData, outfile)


	# logging out
	logoutURL = 'https://cookidoo.'+str(locale)+'/profile/logout'
	brw.get(logoutURL)
	time.sleep(PAGELOAD_TO)
	
	# closing session
	print('[CD] Closing session\n[CD] Goodbye!')
	brw.close()

if  __name__ =='__main__':
	parser = argparse.ArgumentParser(description='Dump Cookidoo recipes from a valid account')
	parser.add_argument('webdriverfile', type=str, help='the path to the Chrome WebDriver file')
	parser.add_argument('outputdir', type=str, help='the output directory')
	parser.add_argument('-s', '--separate-json', dest='separateJson', default=False,
						type=lambda arg: (str(arg).lower() in ['true', '1', 'yes']),
						help='Create separate json file for each recipe. Otherwise generate one data file')
	args = parser.parse_args()
	run(args.webdriverfile, args.outputdir, args.separateJson)
