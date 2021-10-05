import behave_webdriver
from selenium.webdriver.firefox.options import Options
from datetime import datetime

def before_all(context):
    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.headless = True

    context.behave_driver = behave_webdriver.Firefox(options=options)

def after_all(context):
    # Explicitly quits the browser, otherwise it won't once tests are done
    context.behave_driver.quit()

def after_step(context, step):
    if step.status == "failed":
        now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        context.behave_driver.get_screenshot_as_file('screenshot-%s.png' % now)
