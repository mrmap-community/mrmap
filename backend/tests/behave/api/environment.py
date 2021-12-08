from behave.model_core import Status
from behave_django.testcase import BehaviorDrivenTestCase
from rest_framework.test import APIClient


def before_scenario(context, scenario):
    # https://github.com/behave/behave-django/issues/77
    BehaviorDrivenTestCase.port = 8000
    context.client = APIClient()
    context.query_params = {}

    context.fixture = ['test_default_scenario.json']


def after_step(context, step):
    if step.status == Status.failed and context.response:
        print(context.response.content)
