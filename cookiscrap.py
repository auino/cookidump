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

def run():
	"""Scraps all recipes and stores them in html"""
	print('[CS] Starting things off')
	b = startBrowser()
	n = 0
	idsTotal = []
	ids = []

	#login page
	b.get('https://cookidoo.pt/foundation/pt-PT')
	input('[CS] Please login to your account and then press enter to continue:')
	print('[CS] Proceeding with scrapping')

	ids = getIdsOfPage(b, n)
	idsTotal += ids
	n += 1
	while len(ids) > 0:
		ids = getIdsOfPage(b, n)
		idsTotal += ids
		print('\r[CS] {} ids retrieved from page {} | Total ids retrieved: {}'.format(len(ids), n, len(idsTotal)))
		n += 1

	with open('ids.txt', 'a') as f:
		f.write(str(idsTotal))
	print('[CS] Stored ids in txt file')

	i = 0
	j = len(idsTotal)
	for id in idsTotal:
		recipeToFile(b, id, 'recipes')
		i += 1
		print('\r[CS] {}/{} recipes stored'.format(i, j))
	
	print('[CS] closing session\n[CS] goodbye!')
	b.close()

if  __name__ =='__main__':run()