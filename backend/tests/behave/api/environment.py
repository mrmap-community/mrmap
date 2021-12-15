from behave.model_core import Status
from behave_django.testcase import BehaviorDrivenTestCase
from rest_framework.test import APIClient


def before_scenario(context, scenario):
    # https://github.com/behave/behave-django/issues/77
    BehaviorDrivenTestCase.port = 8000
    context.client = APIClient()
    context.query_params = {}
    context.patchers = []

    # basicly there are users, groups and keywords
    context.fixtures = ['test_users.json', 'test_keywords.json']

    if 'MapContext' in scenario.feature.name:
        context.fixtures.append('test_mapcontext.json')
    elif 'DatasetMetadata' in scenario.feature.name:
        context.fixtures.append('test_datasetmetadata.json')


def after_scenario(context, scenario):
    for patcher in context.patchers:
        patcher.stop()


def after_step(context, step):
    if step.status == Status.failed and context.response:
        print(context.response.content)
