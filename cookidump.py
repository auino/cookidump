#!/usr/bin/python3

# cookidump
# Original GitHub project:
# https://github.com/auino/cookidump

import os
import io
import sys
import getpass
import argparse
import platform
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

def getAllIds(browser, baseURL):
	"""Returns ids of recipes in page number as string list"""
	ids, idsTotal, links = [], [], []
	browser.get(baseURL)
	tags = browser.find_elements_by_class_name('wf-tag-cloud__tag')

	for tag in tags: links.append(tag.get_attribute('href'))
	
	nTag = 1
	nTags = len(tags)
	for link in links:
		n = 0

		# Do while
		browser.get('{}&page={}'.format(link, str(n)))
		elems = browser.find_elements_by_tag_name('core-tile')
		if len(elems) > 0:
			for elem in elems:
				ids.append(elem.get_attribute('id'))
			idsTotal += ids
			n += 1

		while len(ids) > 0:
			ids = []
			browser.get('{}&page={}'.format(link, str(n)))
			elems = browser.find_elements_by_tag_name('core-tile')
			if len(elems) > 0:
				for elem in elems:
					ids.append(elem.get_attribute('id'))
				idsTotal += ids
				n += 1
		
		print('\r[CS] {}/{} tags retrieved | Total ids retrieved: {}'.format(nTag, nTags, len(idsTotal)))
		nTag += 1
	return idsTotal

def startBrowser(chrome_driver_path):
    """Starts browser with predefined parameters"""
    #chrome_driver_path = 'chromedriver.exe'
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    driver = webdriver.Chrome(executable_path=chrome_driver_path, chrome_options=chrome_options)
    return driver

def getRecipeBaseURL(browser):
	"""Gets the base URL to use with the recipe ID"""
	link =  browser.find_element_by_class_name('link--alt')
	url = link.get_attribute('href')
	baseURL = url[0:url.find('/r', len(url)-10)+1]
	return baseURL

def recipeToFile(browser, id, baseDir, baseURL):
    """Gets html by recipe id and saves in html file"""
    browser.get(baseURL+str(id))
    html = browser.page_source
    with io.open(baseDir+id+'.html', 'w', encoding='utf-8') as f: f.write(html)

def getFiles(mypath):
	"""Adds all the filenames inside a folder to a list"""
	#https://stackoverflow.com/questions/3207219/how-do-i-list-all-files-of-a-directory
	fileList = [f for f in os.listdir(mypath) if os.path.isfile(os.path.join(mypath, f))]
	return fileList

def getInput(prompText):
	"""Makes a prompt in command line with the correct function call, Python v2 or v3"""
	answer = ''
	if sys.version_info[0] < 3:
		answer = raw_input(prompText)
	else:
		answer = input(prompText)
	return answer

def login(browser):
	"""Logs in account with requested credentials"""
	#Get all navbar links
	elements = browser.find_elements_by_class_name('core-nav__link')
	#Open last link for login
	browser.get(elements[-1].get_attribute('href'))
	print('[CD] Please fill in the login credentials')
	#Find email textbox
	elements=browser.find_element_by_name('j_username')
	userEmail = getInput('[CD] Email: ')
	#Type in email
	elements.send_keys(userEmail)
	#Find password textbox
	elements=browser.find_element_by_name('j_password')
	userPass = getpass.getpass('[CD] Password: ')
	#Type in password
	elements.send_keys(userPass)
	elements.send_keys(Keys.RETURN)

def isDownloaded(fileList, id):
	try:
		fileIndex = fileList.index('{}.html'.format(id))
	except:
		fileIndex = -1
	
	if fileIndex > 0:
		answer = True
	else:
		answer = False
	return answer

def run(webdriverfile, outputdir, locale):
	"""Scraps all recipes and stores them in html"""
	print('[CD] Welcome to cookidump, starting things off...')

	# dir_separator = '/'
	# if str(platform.system()) == 'Windows': dir_separator = '\\'

	baseURL = 'https://cookidoo.{}/'.format(locale)
	print('[CD] Accessing {}'.format(baseURL))

	brw = startBrowser(webdriverfile)
	idsTotal, idsDownloaded = [], [] 

	#login page
	brw.get(baseURL)

	#TODO check if URL contains '/foundation/'
	#if not, program will not work...
	#brw.current_url.contains('/foundation/')

	rbURL = getRecipeBaseURL(brw)

	login(brw)
	print('[CD] Proceeding with scraping')

	#Creating necessary folder
	if not os.path.exists(outputdir): os.makedirs(outputdir)

	#Fetching all the IDs
	idsTotal = getAllIds(brw, baseURL)

	#Writing fetched IDs to a file
	with open('ids.txt', 'w') as f: f.write(str(idsTotal))
	print('[CD] Stored ids in ids.txt file')

	#Checking which files are already downloaded
	files = getFiles(outputdir)

	#Downloading all the recipes
	i = 0
	j = len(idsTotal)
	for id in idsTotal:
		if not isDownloaded(files, id):
			recipeToFile(brw, id, outputdir, rbURL)
			idsDownloaded.append(id)
		i += 1
		print('\r[CD] {}/{} recipes processed'.format(i, j))
	
	#Writing all the downloaded IDs to a file
	with open('idsDownloaded.txt', 'w') as f:
		f.write(str(idsDownloaded))
	print('[CD] {} ids downloaded, ids stored in IdsDownloaded.txt file'.format(len(idsDownloaded)))

	print('[CD] Closing session\n[CD] Goodbye!')
	brw.close()

if  __name__ =='__main__':
	exampleText = '''example:
	python cookidump.py ./chromedriver /home/cooki/recipes it'''
	parser = argparse.ArgumentParser(description='Dump Cookidoo recipes from a valid account', epilog=exampleText)
	parser.add_argument('webdriverfile', type=str, help='the path to the Chrome WebDriver file')
	parser.add_argument('outputdir', type=str, help='the output directory')
	parser.add_argument('locale', type=str, help='locale domain')
	args = parser.parse_args()
	run(args.webdriverfile, args.outputdir, args.locale)
