from behave.model_core import Status
from behave_django.testcase import BehaviorDrivenTestCase
from rest_framework.test import APIClient


def before_scenario(context, scenario):
    # https://github.com/behave/behave-django/issues/77
    BehaviorDrivenTestCase.port = 8000
    context.client = APIClient()
    context.query_params = {}

    # TODO: move test_mapcontext.json fixture loading to before_scenario for features where the name contains MapContext
    context.fixtures = ['test_users.json', 'test_mapcontext.json']


def after_step(context, step):
    if step.status == Status.failed and context.response:
        print(context.response.content)
