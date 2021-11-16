from assertpy import fail
from behave_webdriver.steps import *  # noqa: to get pre defined step definitions

from registry.models import MapContext
from tests.behave.steps.steps import *  # noqa
from behave import given, then


@given('I am logged in as "{username}" with password "{password}"')
def logged_in(context, username, password):
    client = context.test.client
    client.login(username=username, password=password)

    cookie = client.cookies['sessionid']

    # Selenium will set cookie domain based on current page domain.
    context.behave_driver.get(context.get_url('/'))
    context.behave_driver.add_cookie({
        'name': 'sessionid',
        'value': cookie.value,
        'secure': False,
        'path': '/',
    })


@then(
    'I expect a MapContextLayer in the DB that uses WMS Layer "{wms_layer_title}" for selection and belongs to MapContext "{map_context_title}"')
def mapcontext_layer_with_selection(context, wms_layer_title, map_context_title):
    map_context = MapContext.objects.get(title=map_context_title)
    if not map_context:
        fail(f'No MapContext with title {map_context_title} in DB.')
    layer = map_context.mapcontextlayer_set.get(selection_layer__title=wms_layer_title)
    if not layer:
        fail(f'No MapContextLayer that uses WMS Layer {wms_layer_title} for selection.')
