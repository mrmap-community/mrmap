from behave.model_core import Status
from behave_django.testcase import BehaviorDrivenTestCase
from rest_framework.test import APIClient


def before_scenario(context, scenario):
    # https://github.com/behave/behave-django/issues/77
    BehaviorDrivenTestCase.port = 8000
    context.client = APIClient()
    context.query_params = {}
    context.patchers = []

    # basicly there are users and groups
    context.fixtures = ['test_users.json']

    if 'MapContext' in scenario.feature.name:
        context.fixtures.extend(['test_keywords.json', 'test_mapcontext.json'])
    elif 'DatasetMetadata' in scenario.feature.name:
        context.fixtures.extend(
            ['test_keywords.json', 'test_datasetmetadata.json'])
    elif 'AllowedWebMapServiceOperation' in scenario.feature.name:
        context.fixtures.extend(['test_wms.json'])


def after_scenario(context, scenario):
    for patcher in context.patchers:
        patcher.stop()


def after_step(context, step):
    if step.status == Status.failed and context.response:
        print(context.response.content)
