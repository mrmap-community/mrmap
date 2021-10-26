import math
from behave import then, given
from assertpy import fail, assert_that
from jsonpath import jsonpath

from registry.models import Service, Layer, FeatureType, DatasetMetadata, MapContext


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


@then('all {the_class} objects are returned')
def set_impl(context, the_class):
    if the_class == 'services':
        total_number_of_features = Service.objects.count()
    elif the_class == 'layers':
        total_number_of_features = Layer.objects.count()
    elif the_class == 'featuretypes':
        total_number_of_features = FeatureType.objects.count()
    elif the_class == 'dataset_metadata':
        total_number_of_features = DatasetMetadata.objects.count()
    else:
        total_number_of_features = 0

    response = context.response
    results = response.json()

    # the response is actually paginated, and if more than 20 results are in total number of features,
    # then len(results['results']) will be 20
    if int(results['count']) > 20:
        assert_that(len(results['results'])).is_equal_to(20)
        assert_that(int(results['total_pages'])).is_equal_to(math.ceil(int(total_number_of_features)/len(results['results'])))
    else:
        assert_that(len(results['results'])).is_equal_to(int(total_number_of_features))
    assert_that(int(results['count'])).is_equal_to(int(total_number_of_features))


# TODO: refactor to be only one step that makes the call and gives the response, instead of giving the url in a
#  previous step. Needs to be implemented. Currently using the method used by Behave-Rest
@then('{number_of_resources_returned} result(s) is(are) returned, with {search_criteria} as {filter_keyword} criteria')
def set_impl(context, number_of_resources_returned, search_criteria, filter_keyword):
    response = context.response
    results = response.json()

    # the response is actually paginated, and if more than 20 results are in total number of features,
    # then len(results['results']) will be 20
    if int(results['count']) > 20:
        assert_that(len(results['results'])).is_equal_to(20)
        assert_that(int(results['total_pages'])).is_equal_to(math.ceil(int(number_of_resources_returned) / len(results['results'])))
    else:
        assert_that(len(results['results'])).is_equal_to(int(number_of_resources_returned))
    assert_that(int(results['count'])).is_equal_to(int(number_of_resources_returned))


# TODO: refactor to be only one step that makes the call and gives the response, instead of giving the url in a
#  previous step. Needs to be implemented. Currently using the method used by Behave-Rest
@then('{number_of_resources_returned} result(s) is(are) returned, between {start_date} and {end_date} as'
      '{filter_keyword} range criteria')
def set_impl(context, number_of_resources_returned, start_date, end_date, filter_keyword):
    response = context.response
    results = response.json()

    # the response is actually paginated, and if more than 20 results are in total number of features,
    # then len(results['results']) will be 20
    if int(results['count']) > 20:
        assert_that(len(results['results'])).is_equal_to(20)
        assert_that(int(results['total_pages'])).is_equal_to(math.ceil(int(number_of_resources_returned) / len(results['results'])))
    else:
        assert_that(len(results['results'])).is_equal_to(int(number_of_resources_returned))
    assert_that(int(results['count'])).is_equal_to(int(number_of_resources_returned))


# TODO: refactor to be only one step that makes the call and gives the response, instead of giving the url in a
#  previous step. Needs to be implemented. Currently using the method used by Behave-Rest
@then('{number_of_resources_returned} result(s) is(are) returned, when BoundingBox {bbox_array} intersects with {the_class} features')
def set_impl(context, number_of_resources_returned, bbox_array, the_class):
    response = context.response
    results = response.json()

    # the response is actually paginated, and if more than 20 results are in total number of features,
    # then len(results['results']) will be 20
    if int(results['count']) > 20:
        assert_that(len(results['results'])).is_equal_to(20)
        assert_that(int(results['total_pages'])).is_equal_to(math.ceil(int(number_of_resources_returned) / len(results['results'])))
    else:
        assert_that(len(results['results'])).is_equal_to(int(number_of_resources_returned))
    assert_that(int(results['count'])).is_equal_to(int(number_of_resources_returned))


@then('a paginated response is returned')
def set_impl(context):
    response = context.response
    results = response.json()

    assert_that('count' in results.keys()).is_true()
    assert_that('next' in results.keys()).is_true()
    assert_that('previous' in results.keys()).is_true()
    assert_that('total_pages' in results.keys()).is_true()
    assert_that('results' in results.keys()).is_true()


@then('response objects are ordered {order_criteria} by {order_parameter}')
def set_impl(context, order_criteria, order_parameter):
    response = context.response
    results = response.json()

    results_list = list()

    for result in results['results']:
        results_list.append(result[order_parameter])

    sorted_result_list = sorted(results_list) if order_criteria == 'ascending' else sorted(results_list, reverse=True)

    assert_that(results_list).is_equal_to(sorted_result_list)


@then('"accessible" key is part of the response')
def set_impl(context):
    response = context.response
    results = response.json()

    assert_that('accessible' in result.keys() for result in results['results']).is_true()
