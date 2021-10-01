from users.models import MrMapUser
from behave import step, given
from behave_webdriver.steps import *  # noqa: to get pre defined step definitions


@step(u'there are set of Users in Database')
def create_test_users(context):
    for row in context.table:
        MrMapUser.objects.create_user(username=row['username'], password=row['password'])


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
