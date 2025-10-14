# cookidump

List and export recipes from your Cookidoo collections.

### Preamble ###

This is a community-driven project shared within the [original repository](https://github.com/auino/cookidump).
Consider that code has not been analyzed and tested in detail.

Contributors:
* [@ndjc](https://github.com/ndjc) (see [related issue](https://github.com/auino/cookidump/issues/36#issuecomment-3393639812))

### Description ###

This program allows you to list and export recipes from your created and saved collections on Cookidoo.
The export is in JSON compatible with Paprika 3.

In order to list or export the recipes, a valid subscription is needed.

## Significant changes from the original

The code has been modified using Claude AI, as well as human edits!

The method used to find recipes is based on collections and recipe lists, not on Cookidoo queries.

The lxml library is used to parse pages instead of BeautifulSoup, as there seemed to be correctness problems with the latter
(and anyway, lxml is faster).

Collection and recipe parsing is done in parallel threads for performance reasons.

## Installing dependencies

1. Install Python 3
1. Install Python dependencies for the dumpCollections.py script:

        pip3 install -U -r requirements.txt

3. Download the [Chrome WebDriver](https://sites.google.com/chromium.org/driver/),
   naming it appropriately for the current architecture,
   and update the script ``cookidump`` if needed for your architecture.

1. Install [npm](https://www.npmjs.com)

1. Install [prettier](https://prettier.io), and the plugin [prettier-plugin-sort-json](https://www.npmjs.com/package/prettier-plugin-sort-json)

## Running the script

```
cookidump [-r recipes_folder] [-p pattern] [-l locale] [+|-h] [-s]
```

where:

 * ``-r recipes_folder``
   names a folder (directory) where the lists of recipes in each collection will go
   If this option is *not* specified, the default is ``./recipes``.<br><br>

 * ``-p pattern``
   provides a filter for deciding which collections and/or recipes will be dumped.
   The pattern is of the form ``regular_expression[::regular_expression]``.
   The first regular expression is used to match collection names; only collections matching the given regular expression are listed.
   The second regular expression (if given) is used to match recipes; recipes matching the given regular expression are dumped to JSON files.
   If you want to dump certain recipes from any collection, use a filter of the form ``.::recipe_pattern``; the initial dot will match all collections.
   If you want to dump all recipes from certain collections, use a filter of the form ``collection_pattern::.``.

 * ``-l locale``
     provides a locale name, which the program uses to derive the URL for Cookidoo. This has not been tested for all possible Cookidoo locales.

 * ``+h | -h``
     The program opens a [Google ChromeDriver](https://chrome.google.com) session.
     With the -h flag, or if no +/-h flag is provided but authentication cookies have been saved, the session runs headless.
     If +h is specified, the session runs interactively regardless of the presence of authentication cookies.
     If no authentication cookies have yet been saved, or if the cookie is out of date, you will be prompted to enter a user name and password;
     authentication cookies are then saved using that information.

* ``-s``
    All saved collections (as opposed to your own recipe lists, bookmarks, and created recipes) are processed,
    as if you had specified their names in the ``-p`` option.

The program creates a file per created or saved collection, plus one for your bookmarks, plus one for your created recipes.
That file contains lines such as:

```
r470647 https://cookidoo.thermomix.com/recipes/recipe/en-US/r470647 Sesame Orange Chicken
```
- the recipe id (such as r470647), which is a globally unique ID for the recipe (a recipe has that same ID in all instances of Cookidoo),
- the recipe URL (which starts off differently in each Cookidoo regional instance, but ends with the same recipe ID),
- and the recipe name.

The program also creates a couple of index files, containing the names of your collections and the number of recipes in that collection.

A log file, log.txt, is also created, showing timing information that can be used when trrying to optimize performance.

### Disclaimer ###

The authors of this program are not responsible of the usage of it.
This program is released only for research and dissemination purposes.
Also, the program provides users the ability to locally and temporarily store recipes accessible through a legit subscription.
Before using this program, check Cookidoo subscription terms of service, according to the country related to the exploited subscription.
Sharing of the obtained recipes is not a legit activity and the authors of this program are not responsible of any illicit and sharing activity accomplished by the users.

This program is derived from [auino/cookidump](https://github.com/auino/cookidump);
see that program for origins, citations, disclaimers, etc.

