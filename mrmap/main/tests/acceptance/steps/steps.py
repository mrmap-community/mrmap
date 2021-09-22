from users.models import MrMapUser
from behave import step
from behave_webdriver.steps import *  # noqa: to get pre defined step definitions

@step(u'there are set of Users in Database')
def create_test_users(context):
    for row in context.table:
        MrMapUser.objects.create_user(username=row['username'], password=row['password'])

