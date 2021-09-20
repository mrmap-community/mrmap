from users.models import MrMapUser
from behave import given

@given(u'User "{username}" with "{password}" is stored at the database')
def create_test_user(context, username, password):
    test_user = MrMapUser.objects.create_user(username=username, password=password)

@given(u'User "{username}" is not logged in')
def check_user_is_not_logged_in(context, username):
    print(MrMapUser.objects.get(username=username).is_authenticated)
    context.test.assertFalse(MrMapUser.objects.get(username=username).is_authenticated, msg=f"User {username} is authenticated but shouldnt")
