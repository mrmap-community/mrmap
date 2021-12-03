import os
import behave_restful.app as br_app
from behave_django.testcase import BehaviorDrivenTestCase

from requests import Session
from requests.auth import HTTPBasicAuth


# Hook invocations according to https://github.com/behave-restful/behave-restful
def before_all(context):
    context.fixtures = ['scenario_dwd.json']

    this_directory = os.path.abspath(os.path.dirname(__file__))
    br_app.BehaveRestfulApp().initialize_context(context, this_directory)
    context.hooks.invoke(br_app.BEFORE_ALL, context)


def after_all(context):
    context.hooks.invoke(br_app.AFTER_ALL, context)


def before_feature(context, feature):
    context.hooks.invoke(br_app.BEFORE_FEATURE, context, feature)


def after_feature(context, feature):
    context.hooks.invoke(br_app.AFTER_FEATURE, context, feature)


def before_scenario(context, scenario):
    # Authenticate user before a scenario
    # (solution seen here : https://github.com/behave-restful/behave-restful/issues/42)
    context.authorized_session = Session()
    context.authorized_session.auth = HTTPBasicAuth('mrmap', 'mrmap')

    BehaviorDrivenTestCase.port = 8000  # https://github.com/behave/behave-django/issues/77
    context.hooks.invoke(br_app.BEFORE_SCENARIO, context, scenario)


def after_scenario(context, scenario):
    # Close the session after each scenario. Idea is to have a clean session for each scenario
    context.authorized_session.close()

    context.hooks.invoke(br_app.AFTER_SCENARIO, context, scenario)


def before_step(context, step):
    context.hooks.invoke(br_app.BEFORE_STEP, context, step)


def after_step(context, step):
    context.hooks.invoke(br_app.AFTER_STEP, context, step)


def before_tag(context, tag):
    context.hooks.invoke(br_app.BEFORE_TAG, context, tag)


def after_tag(context, tag):
    context.hooks.invoke(br_app.AFTER_TAG, context, tag)