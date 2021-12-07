from behave.model_core import Status
from behave_django.testcase import BehaviorDrivenTestCase
from rest_framework.test import APIClient
from tests.test_data.factory import FixtureBuilder


def before_scenario(context, scenario):
    # https://github.com/behave/behave-django/issues/77
    BehaviorDrivenTestCase.port = 8000
    context.client = APIClient()

    if 'MapContext' in scenario.feature.name:
        fb = FixtureBuilder()
        fb.build_mapcontext_scenario()


def after_step(context, step):
    if step.status == Status.failed and context.response:
        print(context.response.content)
