import os

from behave.model_core import Status
from behave_django.testcase import BehaviorDrivenTestCase
from rest_framework.test import APIClient


def before_scenario(context, scenario):
    # https://github.com/behave/behave-django/issues/77
    BehaviorDrivenTestCase.port = 8000
    context.client = APIClient()


def after_step(context, step):
    if step.status == Status.failed:
        print(context.response.content)
