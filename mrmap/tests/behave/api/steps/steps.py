from behave_restful.lang import *  # noqa : import all pre defined steps of behave_restful package.
from assertpy import fail
from jsonpath import jsonpath
from users.models import MrMapUser
from behave import step, given, then


@given('an authorized session')
def step_auth_session(context):
    context.session = context.authorized_session


@given('an unauthorized session')
def step_unauth_session(context):
    context.session = context.default_session


@then('the response json at {json_path} is missing')
def step_impl(context, json_path):
    json_body = context.response
    json_path = context.vars.resolve(json_path)
    results = jsonpath(json_body, json_path)
    if results:
        fail('Match found at <{path}> for <{body}>'.format(path=json_path, body=json_body))
