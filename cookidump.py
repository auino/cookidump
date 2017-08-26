#!/bin/python

import os
import re
import sys
import json
import shutil
import urllib2
import argparse

# arguments parsing
parser = argparse.ArgumentParser(description='Dump Cookidoo recipes')
parser.add_argument('domain', type=str, help='the cookidoo domain to be used (e.g. cookidoo.it)')
parser.add_argument('outputdir', type=str, help='the output directory')
parser.add_argument('-c', '--recipescount', type=int, help='the number of recipes to dump', default=1455)
parser.add_argument('authorization', type=str, help='the authorization bearer (see https://github.com/auino/cookidump for more information)')
args = parser.parse_args()

# arguments retrieval
DOMAIN = args.domain
BEARER = args.authorization
OUTPUTDIR = args.outputdir
LIMIT = args.recipescount
OUTPUTFILE = OUTPUTDIR+('/' if OUTPUTDIR[-1:] != '/' else '')+'CookiDump'

# useful variables creation
TMPDIR = '/tmp/cookidump/'
BASEURL = 'https://'+DOMAIN
BROWSEURL = BASEURL+'/vorwerkApiV2/apiv2/browseRecipe?limit='+str(LIMIT)
#RECIPEBASEURL = BASEURL+'/vorwerkWebapp/app#/recipe/'
RECIPEBASEURL = BASEURL+'/vorwerkApiV2/apiv2/recipe/'

# gets the image of a recipe (the biggest image possible)
def getrecipeimage(r):
	needle = 'ipad_recipe_thumb_large'
	res = None
	for i in r['imageSlots']:
		res = i['url']
		if i['name'] == needle: return res
	return res

# gets the id of a recipe
def getrecipeid(r):
	try:
		url = r['links'][0]['href']+'/'
		res = re.search('/browseRecipe/(.+)/', url, flags=re.IGNORECASE).group(1)
		if '/' in res: res = res[:res.index('/')]
		return res
	except Exception, e:
		print str(e)
		return None

# generates the recipe url based on the recipe id
def getrecipeurl(r):
	recipeid = getrecipeid(r)
	return RECIPEBASEURL+recipeid

# gets recipe times
def getrecipetime(r, needle, field='value'):
	for t in r['times']:
		try:
			if t['type'].upper() == needle.upper(): return t[field]
		except: pass
	return None

# downloads information from the cookidoo website
def geturldata(url):
	try:
		headers = {"Authorization": BEARER}
		request = urllib2.Request(url, headers=headers)
		contents = urllib2.urlopen(request).read()
		res = json.loads(contents)
		return res
	except Exception, e:
		if e.code == 401: print 'You are not authorized to get recipes.\nPlease try updating your authorization bearer (see https://github.com/auino/cookidump for more information).'
		else: print str(e)
		exit(2)

# gets the recipes list
def getrecipeslist():
	return geturldata(BROWSEURL)

# gets the recipe given an input url
def getrecipe(url):
	return geturldata(url)

# the list of all found recipes
recipes = []

# cycling on found recipes
for recipe in getrecipeslist()['content']:
	# generating the recipe object
	recipe_obj = {
		'id': getrecipeid(recipe),
		'name': recipe['name'],
		'image': getrecipeimage(recipe),
		'url': getrecipeurl(recipe),
		'v1Id': recipe['v1Id'],
		'portion': recipe['portion']['value'],
		'times': {
			'total': getrecipetime(recipe, 'total_time'),
			'active': getrecipetime(recipe, 'active_time'),
			'waiting': getrecipetime(recipe, 'waiting_time'),
			'baking': getrecipetime(recipe, 'baking_time'),
			'baking_from': getrecipetime(recipe, 'baking_time', field='from'),
			'baking_to': getrecipetime(recipe, 'baking_time', field='to'),
			'thermomix': getrecipetime(recipe, 'thermomix_time')
		},
		'fulldata': recipe
	}
	# adding the recipe object to the recipes list
	recipes.append(recipe_obj)

# output file generation

# removing the temporary directory, if already existent
try: os.remove(TMPDIR)
except: pass

# creating the temporary directory again
if not os.path.exists(TMPDIR): os.makedirs(TMPDIR)

# cycling on found recipes
for r in recipes:
	# getting recipe details
	r['recipe'] = getrecipe(r['url'])
	# writing the recipe as a json file
	out_file = open(TMPDIR+'recipe_'+r['id']+'.json', 'w')
	out_file.write(json.dumps(r))
	out_file.close()

# removing the output zip file, if already existent
if os.path.isfile(OUTPUTFILE): os.remove(OUTPUTFILE)

# creating the output zip file
shutil.make_archive(OUTPUTFILE, 'zip', TMPDIR)

# removing the temporary directory
shutil.rmtree(TMPDIR)
