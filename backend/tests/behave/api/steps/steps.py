from accounts.models import User
from behave import given, step, then
from guardian.shortcuts import assign_perm
from rest_framework.authtoken.models import Token


@given(u'there are set of Users in Database')
def create_test_users(context):
    for row in context.table:
        User.objects.create_user(
            username=row['username'], password=row['password'])


@step(u'the user {username} has {permission} permission')
def step_impl(context, username, permission):
    assign_perm(
        perm=permission,
        user_or_group=User.objects.get(username=username)
    )


@step(u'I am logged in as {username} with password {password}')
def step_impl(context, username, password):
    context.client.login(username=username, password=password)


@step(u'I logout the current user')
def step_impl(context,):
    context.client.logout()


@step(u'I use token authentication as {username}')
def step_impl(context, username):
    token = Token.objects.get_or_create(user__username=username)
    context.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)


@step(u'I enforce csrf checks')
def step_impl(context):
    context.client.enforce_csrf_checks = True


@step(u'I use the endpoint {url}')
def step_impl(context, url):
    context.endpoint = url


@given(u'I set the request payload to')
def step_impl(context):
    context.payload = context.text


@step(u'I set the content type of the request to {content_type}')
def step_impl(context, content_type):
    context.content_type = content_type


@step(u'I send the request with GET method')
def step_impl(context):
    context.response = context.client.get(path=context.endpoint)


@step(u'I send the request with PATCH method')
def step_impl(context):
    context.response = context.client.patch(
        path=context.endpoint,
        data=context.payload,
        content_type=context.content_type if hasattr(context, 'content_type') else 'application/json')


@step(u'I send the request with POST method')
def step_impl(context):
    context.response = context.client.post(
        path=context.endpoint,
        data=context.payload,
        content_type=context.content_type if hasattr(context, 'content_type') else 'application/json')


@step(u'I send the request with DELETE method')
def step_impl(context):
    context.response = context.client.delete(
        path=context.endpoint)


@then('I expect the response status is {expected_status}')
def step_impl(context, expected_status: int):
    context.test.assertEqual(
        context.response.status_code, int(expected_status))
