
from selenium import webdriver

def before_all(context):
	# PhantomJS is used there (headless browser - meaning we can execute tests in a command-line environment, which is what we want for use with SemaphoreCI
	# For debugging purposes, you can use the Firefox driver instead.

	context.browser = webdriver.PhantomJS()
	context.browser.implicitly_wait(1)
	context.server_url = 'http://localhost'

def after_all(context):
	# Explicitly quits the browser, otherwise it won't once tests are done
	context.browser.quit()

def before_feature(context, feature):
	# Code to be executed each time a feature is going to be tested
	pass

