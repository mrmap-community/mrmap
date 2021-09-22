import behave_webdriver


def before_all(context):
    context.behave_driver = behave_webdriver.Firefox.headless()
    print('before_all')
    pass

def after_all(context):
	# Explicitly quits the browser, otherwise it won't once tests are done
	context.behave_driver.quit()
	print('after_all')
	pass

def before_feature(context, feature):
	# Code to be executed each time a feature is going to be tested
	print('before_feature')
	pass

