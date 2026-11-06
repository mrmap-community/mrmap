@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json
Feature: DatasetMetadataRecord List Endpoint
    As an API client,
    I want to search dataset metadata records,
    so that I can search for.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    Scenario: Can retrieve list as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"

    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action             | param                                | value                           | count |
            | search             | filter[search]                       | niederschlag                    | 1     |
            | filter by keywords | filter[keywords__keyword__icontains] | niederschlag                    | 1     |
            | filter by title    | filter[title__icontains]             | Relative Feuchte                | 1     |
            | filter by abstract | filter[abstract__icontains]          | Messwerte der relativen Feuchte | 1     |

    # A search word is a word of the record: of its title, of its abstract or of one
    # of its keywords, which is what the vector of the record holds. A piece of a
    # word is not a word and finds nothing, which is what makes the search answerable
    # by the index of that vector instead of a pattern scan over the keyword
    # relation of the whole catalogue (#1029).
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                        | param          | value            | count |
            | search by a word of a keyword | filter[search] | luftfeuchtigkeit | 1     |
            | search by words of one record | filter[search] | relative feuchte | 1     |
            | search by a word of both      | filter[search] | messwerte        | 2     |
            | search a piece of a word      | filter[search] | niederschla      | 0     |

    # The generated filterset offers the uuid lookups on the primary key and a case sensitive
    # `contains` next to the `icontains` rows above.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                   | param                     | value                                  | count |
            | filter by id             | filter[id]                | d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4  | 1     |
            | filter by id in          | filter[id.in]             | d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4  | 1     |
            | filter by id in          | filter[id.in]             | d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4,9e57ada9-d3bf-403f-bd6c-eb4d38f0ef8e | 2 |
            | filter by title contains | filter[title.contains]    | Relative                             | 1     |
            | filter by title contains | filter[title.contains]    | relative                             | 0     |

    # The list of dataset metadata records of the frontend is ordered by the title of the record.
    Scenario Outline: Can sort records by their title
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering | first                                |
            | title    | d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4  |
            | -title   | 9e57ada9-d3bf-403f-bd6c-eb4d38f0ef8e  |
