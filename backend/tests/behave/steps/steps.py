from auth.models import User
from behave import step


@step(u'there are set of Users in Database')
def create_test_users(context):
    for row in context.table:
        User.objects.create_user(
            username=row['username'], password=row['password'])
