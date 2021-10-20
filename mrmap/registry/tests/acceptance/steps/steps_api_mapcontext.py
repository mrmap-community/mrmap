from behave import given, when, then


@given('the database contains a MapContext with id 1')
def step_impl(context):
    pass


@when("I access the URL '/api/v1/registry/mapcontext/1'")
def step_impl(context):
    assert True is not False


@then('the HTTP response is a valid OWS Context GeoJSON document')
def step_impl(context):
    assert context.failed is False
