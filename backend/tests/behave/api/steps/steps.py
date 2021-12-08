from behave import given, step, then
from rest_framework.authtoken.models import Token


@step('I am logged in as {username} with password {password}')
def step_impl(context, username, password):
    context.client.login(username=username, password=password)


@step('I logout the current user')
def step_impl(context,):
    context.client.logout()


@step('I use token authentication as {username}')
def step_impl(context, username):
    token = Token.objects.get_or_create(user__username=username)
    context.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)


@step('I enforce csrf checks')
def step_impl(context):
    context.client.enforce_csrf_checks = True


@step('I use the endpoint {url}')
def step_impl(context, url):
    context.endpoint = url


@given('I set the request payload to')
def step_impl(context):
    context.payload = context.text


@given('I set a queryparam {param} with value {value}')
def step_impl(context, param, value):
    context.query_params.update({param: value})


@step('I set the content type of the request to {content_type}')
def step_impl(context, content_type):
    context.content_type = content_type


@step('I send the request with GET method')
def step_impl(context):
    context.response = context.client.get(
        path=context.endpoint,
        data=context.query_params or None)


@step('I send the request with PATCH method')
def step_impl(context):
    context.response = context.client.patch(
        path=context.endpoint,
        data=context.payload,
        content_type=context.content_type if hasattr(context, 'content_type') else 'application/json',)


@step('I send the request with POST method')
def step_impl(context):
    context.response = context.client.post(
        path=context.endpoint,
        data=context.payload,
        content_type=context.content_type if hasattr(context, 'content_type') else 'application/json')


@step('I send the request with DELETE method')
def step_impl(context):
    context.response = context.client.delete(
        path=context.endpoint)


@then('I expect the response status is {expected_status}')
def step_impl(context, expected_status: int):
    context.test.assertEqual(
        context.response.status_code, int(expected_status))
