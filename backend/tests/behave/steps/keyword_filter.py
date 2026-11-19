"""Domain steps of the keyword list filter (issue #1477).

The keyword filters of registry/filters/metadata.py match over the m2m
relation of the keywords, so a record answering the asked piece with TWO of
its keywords joins twice -- as two rows of the page AND as two rows of the
paginator's count. django-filter adds no DISTINCT unless a filter carries
distinct=True. The first fixture record already holds "Niederschlag"; the
Given step adds the second matching keyword over the ORM -- the scenario
transaction rolls it back, so no other feature ever sees it -- and the Then
step asks the list through the endpoint.
"""

from behave import given, then, when
from registry.models.metadata import DatasetMetadataRecord, Keyword

FIRST_FIXTURE_RECORD = 'd8b50d33-2ad7-4a41-bd0d-2d518ea10fd4'
DATASET_LIST = '/api/registry/dataset-metadata'
JSONAPI = 'application/vnd.api+json'


@given('the fixture record holds a second keyword answering the piece')
def hold_second_keyword(context):
    record = DatasetMetadataRecord.objects.get(pk=FIRST_FIXTURE_RECORD)
    record.keywords.add(Keyword.objects.get(keyword='Niederschlagsdefizit'))


@when('I ask the dataset metadata list for a "{lookup}" filter on the '
      'keyword piece "{piece}"')
def ask_list(context, lookup, piece):
    response = context.client.get(
        f'{DATASET_LIST}?filter[keywords__keyword__{lookup}]={piece}',
        HTTP_ACCEPT=JSONAPI)
    if not response.is_rendered:
        response.render()
    context.keyword_filter_body = response.json()
    context.keyword_filter_status = response.status_code


@then('the list answers the record "{record_id}" once')
def answers_once(context, record_id):
    assert context.keyword_filter_status == 200, context.keyword_filter_body
    ids = [row['id'] for row in context.keyword_filter_body['data']]
    assert ids == [record_id], (
        'the record was answered as many times as it holds matching '
        f'keywords: {ids}')
    count = context.keyword_filter_body['meta']['pagination']['count']
    assert count == 1, f'the paginator counted {count} rows for one record'
