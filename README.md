# cookidump

Easily dump cookidoo recipes from the official website

### Description ###

This program allows you to dump all recipes on [Cookidoo](https://cookidoo.co.uk) websites (available for different countries) for offline and posticipate reading.
Those recipes are valid in particular for [Thermomix/Bimby](https://en.wikipedia.org/wiki/Thermomix) devices.
In order to dump the recipes, a valid subscription is needed.

The initial concept of this program was based on [jakubszalaty/cookidoo-parser](https://github.com/jakubszalaty/cookidoo-parser).

### Features ###

* Easy to run
* Easy to open HTML output
* Output including a surfable list of dumped recipes
* Customizable searches

### Installation ###


1. Clone the repository:

```
git clone https://github.com/auino/cookidump.git
```

2. `cd` into the download folder

3. Install [Python](https://www.python.org) requirements:

```
pip install -r requirements.txt
```

4. Install the [Google Chrome](https://chrome.google.com) browser, if not already installed

5. Download the [Chrome WebDriver](https://sites.google.com/a/chromium.org/chromedriver/) and save it on the `cookidump` folder

6. You are ready to dump your recipes

### Usage ###

Simply run the following command to start the program. The program is interactive to simplify it's usage.

```
python cookidump.py [--separate-json false] <webdriverfile> <outputdir>
```

where:
* `webdriverfile` identifies the path to the downloaded [Chrome WebDriver](https://sites.google.com/a/chromium.org/chromedriver/) (for instance, `chromedriver.exe` for Windows hosts, `./chromedriver` for Linux and macOS hosts)
* `outputdir` identifies the path of the output directory (will be created, if not already existent)

optional arguments:
* `--separate-json` (default: false) allows to generate json files for each recipe instead of one aggregate file

The program will open a [Google Chrome](https://chrome.google.com) window and wait until you are logged in into your [Cookidoo](https://cookidoo.co.uk) account (different countries are supported).

After that, follow intructions provided by the script itself to proceed with the dump.

#### Considerations ####

By following script instructions, it is also possible to apply custom filters to export selected recipes (for instance, in base of the dish, title and ingredients, Thermomix/Bimby version, etc.).

Output is represented by an `index.html` file, included in `outputdir`, plus a set of recipes inside of structured folders.
By opening the generated `index.html` file on your browser, it is possible to have a list of recipes downloaded and surf to the desired recipe.

The number of exported recipes is limited to around `1000` for each execution.
Hence, use of filters may help in this case to reduce the number of recipes exported.

### Other approaches ###

A different approach, previously adopted, is based on the retrieval of structured data on recipes.
More information can be found on the [datastructure branch](https://github.com/auino/cookidump/tree/datastructure).
Output is represented in this case in a different (structured) format, hence, it has to be interpreted. Such interpretation is not implemented in the linked previous commit.

### TODO ###

* Bypass the limited number of exported recipes
* Parse downloaded recipes to store them on a database, or to generate a unique linked PDF
* Make Chrome run headless for better speeds
* Set up a dedicated container for the program

### Supporters ###

* [@vikramsoni2](https://github.com/vikramsoni2), regarding JSON saves plus minor enhancements

### Disclaimer ###

The authors of this program are not responsible of the usage of it.
This program is released only for research and dissemination purposes.
Also, the program provides users the ability to locally and temporarily store recipes accessible through a legit subscription.
Before using this program, check Cookidoo subscription terms of service, according to the country related to the exploited subscription. 
Sharing of the obtained recipes is not a legit activity and the authors of this program are not responsible of any illecit and sharing activity accomplished by the users.

### Contacts ###

You can find me on Twitter as [@auino](https://twitter.com/auino).
