from accounts.models import User
from assertpy import fail
from behave import given, step, then
from behave_restful.lang import *  # noqa : import all pre defined steps of behave_restful package.
from django.test.client import Client
from jsonpath import jsonpath
from requests import Session


@step(u'there are set of Users in Database')
def create_test_users(context):
    for row in context.table:
        User.objects.create_user(
            username=row['username'], password=row['password'])


@given('user {username} with {password} is logged in')
def step_login_user(context, username, password):
    client = Client()
    client.login(username=username, password=password)
    context.session.cookies.update(client.cookies)


@then('the response json at {json_path} is missing')
def step_impl(context, json_path):
    json_body = context.response
    json_path = context.vars.resolve(json_path)
    results = jsonpath(json_body, json_path)
    if results:
        fail('Match found at <{path}> for <{body}>'.format(
            path=json_path, body=json_body))
