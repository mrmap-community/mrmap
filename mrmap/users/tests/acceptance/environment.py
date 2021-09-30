import behave_webdriver
from selenium.webdriver.firefox.options import Options


def before_all(context):
    options = Options()
    options.headless = True

    context.behave_driver = behave_webdriver.Firefox(options=options)
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
