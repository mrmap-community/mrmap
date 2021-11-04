import time
import behave_webdriver
from datetime import datetime
from selenium.webdriver.firefox.options import Options
from datetime import datetime
from behave.model_core import Status
from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException


def before_all(context):
    context.fixtures = ['default_scenario.json']
    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.headless = True

    context.behave_driver = behave_webdriver.Firefox(options=options)


def after_all(context):
    # Explicitly quits the browser, otherwise it won't once tests are done
    context.behave_driver.quit()


def after_step(context, step):
    if step.status == Status.failed:
        now = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        file_name = 'selenium-%(feature)s-%(step_number)d-%(date)s.png' % {"feature": context.scenario.feature.name.replace(" ", "_"), "step_number": step.line, "date": now}
        context.behave_driver.get_screenshot_as_file(file_name)
        
        if isinstance(step.exception, ElementClickInterceptedException) and "is not clickable at point" in step.exception.msg:
            # add a circle to show where the click was done
            x, y = step.exception.msg.split("(")[1].split(")")[0].split(",")
            x = int(x)
            y = int(y)
        
            from PIL import Image, ImageDraw
            with Image.open(file_name) as im:
                draw = ImageDraw.Draw(im)
                draw.ellipse(xy=(x-10, y-10, x+10, y+10), fill=(255, 0, 0), outline=(0, 0, 0))
                im.save(file_name)

            