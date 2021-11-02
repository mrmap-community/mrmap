from behave_webdriver.steps import *  # noqa: to get pre defined step definitions
from tests.behave.steps.steps import *  # noqa
from behave import given


@given('I am logged in')
def impl(context):
    client = context.test.client
    client.login(username='peter', password='password123')

    cookie = client.cookies['sessionid']

    # Selenium will set cookie domain based on current page domain.
    context.behave_driver.get(context.get_url('/'))
    context.behave_driver.add_cookie({
        'name': 'sessionid',
        'value': cookie.value,
        'secure': False,
        'path': '/',
    })
