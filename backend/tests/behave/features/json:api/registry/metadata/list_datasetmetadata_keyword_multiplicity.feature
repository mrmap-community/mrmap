@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_csw.json @fixtures:test_datasetmetadata_matching_keywords.json
Feature: Dataset metadata keyword filters answer each record once
    As an API client,
    I want a keyword filter to answer every matching record exactly once,
    so that the rows of a page and the facet counts answered over the same
    filtered queryset agree (#1477).

    One record carries the two keywords "Niederschlag" and
    "Niederschlagsdefizit". A keyword filter joins the keyword relation, so
    before #1477 the record answered TWICE to filter[keywords__keyword__icontains]
    with value "niederschlag" - django-filter only answers DISTINCT for a
    filter which declares distinct=True, and the generated keyword filters
    did not. The scenarios below are the confirmation the audit asked for:
    one record, two matching keywords, one row.

    Every scenario names the record's id next to the keyword lookup. Fixtures
    are loaded per feature and never restored, so the counts of a scenario
    only answer reliably when the queryset is scoped to the rows of this
    feature; the id is exact and joins nothing, so it pins the environment
    without touching the shape under test - the keyword join multiplies the
    very row the id names. The record and its contact leave the database in
    the after_feature teardown of environment.py, so what runs after this
    feature counts without it.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata

    Scenario: The record alone answers once
        Given I set a queryparam "filter[id]" with value "f1a71477-0000-4000-8000-000000000077"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario: Two matching keywords answer one row for icontains
        Given I set a queryparam "filter[id]" with value "f1a71477-0000-4000-8000-000000000077"
        And I set a queryparam "filter[keywords__keyword__icontains]" with value "niederschlag"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"
        Then I expect that response json has an attribute "data.[0].id" with value "f1a71477-0000-4000-8000-000000000077"

    Scenario: The keyword which does not match the second word answers one row too
        Given I set a queryparam "filter[id]" with value "f1a71477-0000-4000-8000-000000000077"
        And I set a queryparam "filter[keywords__keyword__icontains]" with value "defizit"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario: The case sensitive contains answers one row on its matching word
        Given I set a queryparam "filter[id]" with value "f1a71477-0000-4000-8000-000000000077"
        And I set a queryparam "filter[keywords__keyword__contains]" with value "iederschlagsdefizit"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    Scenario: The exact lookup on one of the two keywords answers one row
        Given I set a queryparam "filter[id]" with value "f1a71477-0000-4000-8000-000000000077"
        And I set a queryparam "filter[keywords__keyword]" with value "Niederschlag"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"
