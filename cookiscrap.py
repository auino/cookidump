#!/usr/bin/python3
import os
import io
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

def getIdsOfPage(browser, page):
	"""Returns ids of recipes in page number as string list"""
	browser.get('https://cookidoo.pt/search/pt-PT?context=recipes&countries=pt&page='+str(page))
	elems = browser.find_elements_by_tag_name('core-tile')
	if len(elems) > 0:
		ids = []
		for elem in elems:
			ids.append(elem.get_attribute('id'))
	else:
		ids = []
	return ids

def getAllIds(browser):
	"""Returns ids of recipes in page number as string list"""
	ids, idsTotal, links = [], [], []
	browser.get('https://cookidoo.pt')
	tags = browser.find_elements_by_class_name('wf-tag-cloud__tag')

	for tag in tags:
		links.append(tag.get_attribute('href'))
	
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

def startBrowser():
    """Starts browser with predefined parameters"""
    chrome_driver_path = 'chromedriver.exe'
    chrome_options = Options()
    #chrome_options.add_argument('--headless')
    driver = webdriver.Chrome(executable_path=chrome_driver_path, chrome_options=chrome_options)
    return driver

def recipeToFile(browser, id, folder):
    """Gets html by recipe id and saves in html file"""
    browser.get('https://cookidoo.pt/recipes/recipe/pt-PT/'+str(id))
    html = browser.page_source
    baseDir = os.getcwd()+'\\{}\\'.format(folder)
    with io.open(baseDir+id+'.html', 'a', encoding='utf-8') as f:
        f.write(html)

def appendToMarkdown(content, file):
    baseDir = os.getcwd() + '\\recipes\\{}.md'.format(file)
    with io.open(baseDir, 'a', encoding='utf-8') as f:
        f.write(content + '\n')

def getFiles(folder):
	#https://stackoverflow.com/questions/3207219/how-do-i-list-all-files-of-a-directory
	mypath = os.getcwd() + '\\{}\\'.format(folder)
	fileList = [f for f in os.listdir(mypath) if os.path.isfile(os.path.join(mypath, f))]
	return fileList

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

def run():
	"""Scraps all recipes and stores them in html"""
	print('[CS] Starting things off')
	brw = startBrowser()
	idsTotal, idsDownloaded = [], []
	activeFolder = 'recipes'
	activePath = os.getcwd() + '\\{}\\'.format(activeFolder)

	#login page
	brw.get('https://cookidoo.pt/foundation/pt-PT')
	input('[CS] Please login to your account and then press enter to continue:')
	print('[CS] Proceeding with scrapping')

	#Creating necessary folder
	if not os.path.exists(activePath):
		os.makedirs(activePath)

	idsTotal = getAllIds(brw)

	with open('idsNew.txt', 'w') as f:
		f.write(str(idsTotal))
	print('[CS] Stored ids in idsNew.txt file')

	files = getFiles(activeFolder)

	i = 0
	j = len(idsTotal)
	for id in idsTotal:
		if not isDownloaded(files, id):
			recipeToFile(brw, id, activeFolder)
			idsDownloaded.append(id)
		i += 1
		print('\r[CS] {}/{} recipes processed'.format(i, j))
	
	with open('idsDownloaded.txt', 'w') as f:
		f.write(str(idsDownloaded))
	print('[CS] {} ids downloaded, ids stored in IdsDownloaded.txt file'.format(len(idsDownloaded)))

	print('[CS] Closing session\n[CS] Goodbye!')
	brw.close()

if  __name__ =='__main__':run()