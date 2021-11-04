import behave_webdriver
from datetime import datetime
from selenium.webdriver.firefox.options import Options
from datetime import datetime
from behave.model_core import Status
from selenium.common.exceptions import NoSuchElementException


def before_all(context):
    context.fixtures = ['scenario_dwd.json']
    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.headless = True

    context.behave_driver = behave_webdriver.Firefox(options=options)


def after_all(context):
    # Explicitly quits the browser, otherwise it won't once tests are done
    context.behave_driver.quit()


def before_step(context, step):
    ele = context.behave_driver.find_element("xpath", '//body')
    context.behave_driver.set_window_size(1920, ele.size["height"] + 1000)  # to get the full page with one screenshot


def after_step(context, step):
    if step.status == Status.failed:
        now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        context.behave_driver.maximize_window()
        try:
            ele=context.behave_driver.find_element("xpath", '//body')
            context.behave_driver.set_window_size(1920, ele.size["height"] + 1000)  # to get the full page with one screenshot
        except NoSuchElementException:
            pass
        context.behave_driver.get_screenshot_as_file('selenium-%(feature)s-%(step_number)d-%(date)s.png' % {"feature": context.scenario.feature.name.replace(" ", "_"), "step_number": step.line, "date": now})
