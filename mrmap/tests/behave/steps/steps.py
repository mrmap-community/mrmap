import json
from unittest.mock import Mock, patch

from behave import given, step, then
from django.contrib.auth import get_user_model
from django.db import reset_queries
from django.http import SimpleCookie
from knox.models import AuthToken
from lxml import etree
from lxml.etree import fromstring
from rest_framework.authtoken.models import Token


@step('I am logged in as {username} with password {password}')
def step_impl(context, username, password):
    success = context.client.login(username=username, password=password)
    if not success:
        raise Exception(
            f"can't log in user {username} with password {password}")


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


@given('I set a queryparam "{param}" with value "{value}"')
def step_impl(context, param, value):
    context.query_params.update({param: value})


@step('I set the content type of the request to {content_type}')
def step_impl(context, content_type):
    context.content_type = content_type


@step('I send the request with GET method')
def step_impl(context):
    reset_queries()
    request = {
        "path": context.endpoint,
        "data": context.query_params or None,
    }
    if hasattr(context, "headers"):
        request.update(**context.headers)
    context.response = context.client.get(**request)


@step('I send the request with PATCH method')
def step_impl(context):
    reset_queries()
    request = {
        "path": context.endpoint,
        "data": context.payload if hasattr(context, "payload") else None,
        "content_type": context.content_type if hasattr(
            context, 'content_type') else 'application/json',
    }
    if hasattr(context, "headers"):
        request.update(**context.headers)
    context.response = context.client.patch(**request)


@step('I send the request with POST method')
def step_impl(context):
    reset_queries()
    request = {
        "path": context.endpoint,
        "data": context.payload if hasattr(context, "payload") else None,
        "content_type": context.content_type if hasattr(
            context, 'content_type') else 'application/json',
    }
    if hasattr(context, "headers"):
        request.update(**context.headers)
    context.response = context.client.post(**request)


@step('I send the request with DELETE method')
def step_impl(context):
    reset_queries()
    request = {
        "path": context.endpoint,
    }
    if hasattr(context, "headers"):
        request.update(**context.headers)

    context.response = context.client.delete(**request)


@then('I expect the response status is {expected_status}')
def step_impl(context, expected_status: int):
    context.test.assertEqual(
        context.response.status_code, int(expected_status))


@then('I expect that there is a xpath "{xpath}"')
@then('I expect that there is a xpath "{xpath}" with value "{expected_value}"')
def step_impl(context, xpath: str, expected_value: str = None):
    parser = etree.XMLParser(ns_clean=True, recover=True, encoding='utf-8')
    h = fromstring(context.response.content, parser=parser)
    r = h.xpath(xpath)

    if expected_value:
        context.test.assertEqual(
            r[0], expected_value
        )


def _traverse_json(context, attribute):
    keys = attribute.split('.')
    json = context.response.json()
    value = None
    for key in keys:
        if '[' and ']' in key:
            key = int(key.split('[')[-1].split(']')[0])
        value = json[key] if not value else value[key]
    return value


@then('I expect that response json has an attribute "{attribute}"')
@then('I expect that response json has an attribute "{attribute}" with value "{expected_value}"')
def step_impl(context, attribute, expected_value=None):
    value = _traverse_json(context=context, attribute=attribute)
    if expected_value:
        if expected_value == 'false' or expected_value == 'true':
            context.test.assertEqual(bool(value), bool(expected_value))
        else:
            try:
                context.test.assertJSONEqual(str(value), expected_value)
            except Exception as e:
                context.test.assertEqual(str(value), expected_value)


@then('I expect that response xml content is:')
@then(u'I expect that response xml content is')
def step_impl(context):
    context.test.maxDiff = None

    context.test.assertXMLEqual(
        context.response.content.decode("UTF-8").replace("\n", ""), context.text.replace("\n", ""))


@then('I expect that "{expected_value}" queries where made')
def step_impl(context, expected_value):
    context.test.assertNumQueries(expected_value)


@given('I mock the function "{func_name}" of the module "{module_name}" with return value as object')
def step_impl(context, func_name, module_name):
    mock = Mock()
    setattr(mock, func_name, Mock(return_value=json.loads(context.text)))
    patcher = patch(module_name, mock)
    patcher.start()
    context.patchers.append(patcher)

# @then('I expect that the function "{func_name}" of the module "{module_name}" was called with')
# def step_impl(context, func_name, module_name, args, kwargs):
#     callvalues = dict(context.text)


@given('I set the cookie "{cookie_name}" with value "{cookie_value}"')
def step_impl(context, cookie_name, cookie_value):
    if not context.client.cookies:
        context.client.cookies = SimpleCookie()
    context.client.cookies[cookie_name] = cookie_value


@given('I set the header "{header_name}" with value "{header_value}"')
def step_impl(context, header_name, header_value):
    if not hasattr(context, "headers"):
        context.headers = {}
    context.headers.update({header_name: header_value})


@given('I use token based authentication for user "{username}"')
def step_impl(context, username):
    user = get_user_model().objects.get(username=username)
    instance, token = AuthToken.objects.create(
        user=user)
    if not hasattr(context, "headers"):
        context.headers = {}
    context.headers.update({"HTTP_AUTHORIZATION": f"Token {token}"})
