#!/bin/python
# based on https://github.com/jakubszalaty/cookidoo-parser

import os
import re
import sys
import json
import shutil
import urllib2
import argparse

TMPDIR = '/tmp/cookidump/'

parser = argparse.ArgumentParser(description='Dump Cookidoo recipes')
parser.add_argument('domain', type=str, help='the cookidoo domain to be used (e.g. cookidoo.it)')
parser.add_argument('outputdir', type=str, help='the output directory')
parser.add_argument('-c', '--recipescount', type=int, help='the number of recipes to dump', default=1455)
parser.add_argument('authorization', type=str, help='the authorization bearer (see https://github.com/auino/cookidump for more information)')

args = parser.parse_args()

DOMAIN = args.domain
BEARER = args.authorization
OUTPUTDIR = args.outputdir
LIMIT = args.recipescount
OUTPUTFILE = OUTPUTDIR+('/' if OUTPUTDIR[-1:] != '/' else '')+'CookiDump'

BASEURL = 'https://'+DOMAIN
BROWSEURL = BASEURL+'/vorwerkApiV2/apiv2/browseRecipe?limit='+str(LIMIT)
#RECIPEBASEURL = BASEURL+'/vorwerkWebapp/app#/recipe/'
RECIPEBASEURL = BASEURL+'/vorwerkApiV2/apiv2/recipe/'

def getrecipeimage(r):
	needle = 'ipad_recipe_thumb_large'
	res = None
	for i in r['imageSlots']:
		res = i['url']
		if i['name'] == needle: return res
	return res

def getrecipeid(r):
	try:
		url = r['links'][0]['href']+'/'
		res = re.search('/browseRecipe/(.+)/', url, flags=re.IGNORECASE).group(1)
		if '/' in res: res = res[:res.index('/')]
		return res
	except Exception, e:
		print str(e)
		return None

def getrecipeurl(r):
	recipeid = getrecipeid(r)
	#return 'https://cookidoo.it/vorwerkApiV2/apiv2/browseRecipe/'+recipeid+'/'
	return RECIPEBASEURL+recipeid

def getrecipetime(r, needle, field='value'):
	for t in r['times']:
		try:
			if t['type'].upper() == needle.upper(): return t[field]
		except: pass
	return None

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

def getrecipeslist():
	return geturldata(BROWSEURL)

def getrecipe(url):
	return geturldata(url)

def zipdir(path, ziph):
	# ziph is zipfile handle
	for root, dirs, files in os.walk(path):
		for file in files:
			ziph.write(os.path.join(root, file))

recipes = []

for recipe in getrecipeslist()['content']:
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
		}
	}
	recipes.append(recipe_obj)

try: os.remove(TMPDIR)
except: pass

if not os.path.exists(TMPDIR): os.makedirs(TMPDIR)

for r in recipes:
	r['recipe'] = getrecipe(r['url'])
	out_file = open(TMPDIR+'recipe_'+r['id']+'.json', 'w')
	out_file.write(json.dumps(r))
	out_file.close()

shutil.make_archive(OUTPUTFILE, 'zip', TMPDIR)

shutil.rmtree(TMPDIR)
