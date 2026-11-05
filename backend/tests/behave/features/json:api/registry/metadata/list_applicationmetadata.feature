@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_csw.json @fixtures:test_applicationmetadata.json
Feature: ApplicationMetadataRecord List Endpoint
    As an API client,
    I want to list and search application metadata records,
    so that the third record type of the harvesting is as discoverable as the dataset and
    service records.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/application-metadata

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    Scenario: Can retrieve list as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    # The resource type is what the generated client of #831 derives its hook from; the
    # list rows of a json:api collection carry it as the detail answer does.
    Scenario: Answers the json:api resource type of the record
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].type" with value "ApplicationMetadataRecord"

    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action             | param                                | value                              | count |
            | search             | filter[search]                       | niederschlag                       | 1     |
            | filter by keywords | filter[keywords__keyword__icontains] | niederschlag                       | 1     |
            | filter by title    | filter[title__icontains]             | Bericht                            | 1     |
            | filter by abstract | filter[abstract__icontains]          | Wetterbeobachtungen                | 1     |

    # The generated filterset offers the uuid lookups on the primary key and a case
    # sensitive `contains` next to the `icontains` rows above, as on the dataset records.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                   | param                                  | value                                          | count |
            | filter by id             | filter[id]                             | a11c0000-0000-4000-8000-000000000001           | 1     |
            | filter by id in          | filter[id.in]                          | a11c0000-0000-4000-8000-000000000001           | 1     |
            | filter by id in          | filter[id.in]                          | a11c0000-0000-4000-8000-000000000001,a11c0000-0000-4000-8000-000000000002 | 2 |
            | filter by title contains | filter[title.contains]                 | Anwendung N                                      | 1     |
            | filter by title contains | filter[title.contains]                 | anwendung n                                      | 0     |

    # The spatial lookups of the records filterset; only one record of the fixture carries a
    # bounding geometry, so a whole-world rectangle separates the answers (the polygon of the
    # filter is wider than a table cell and stays out of the outlines, as on the layers feature).
    Scenario: Can filter records whose bounding geometry a world rectangle intersects
        Given I set a queryparam "filter[bounding_geometry__intersects]" with value "SRID=4326;POLYGON ((-180 -90, 180 -90, 180 90, -180 90, -180 -90))"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    # The list of application metadata records of the frontend is ordered by the title of
    # the record, as the dataset list is.
    Scenario Outline: Can sort records by their title
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering | first                                |
            | title    | a11c0000-0000-4000-8000-000000000001 |
            | -title   | a11c0000-0000-4000-8000-000000000002 |

    Scenario: Refuses a filter which was never configured
        Given I set a queryparam "filter[not_a_field]" with value "1"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"

    Scenario: Refuses a sort which was never configured
        Given I set a queryparam "sort" with value "not_a_field"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
