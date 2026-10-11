@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: Historical WebMapService List Endpoint
    As an API client,
    I want to search for historical web map services,
    so that I can find relevant changelog.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/historical-wms

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"
        Then I expect that response json has an attribute "data.[0].id" with value "40d6bddd-6e8b-4487-b3ed-ee2a4ac5dee2"
        # TODO: results in slow sql requests
        #Then I expect that response json has an attribute "data.[0].attributes.delta" with value "[{'field': 'abstract', 'old': 'wms1 abstract', 'new': 'wms1 abstract hihi'}, {'field': 'title', 'old': 'WMS1', 'new': 'WMS1 huhu'}]"

        Then I expect that "7" queries where made

    Scenario: Can include historyUser
        Given I set a queryparam "include" with value "historyUser"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "User"

    Scenario: Can include historyRelation
        Given I set a queryparam "include" with value "historyRelation"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "WebMapService"

    # The fixture holds the creation record of WMS1 and one later change of its title. The dates of
    # the two rows are the only difference the date lookups can tell apart, so every row of the
    # first table matches exactly one of them.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                     | param                     | value                                      | count |
            | filter by history date     | filter[historyDate]       | 2022-02-01T13:54:12.013+00:00              | 1     |
            | filter by history date     | filter[historyDate.gte]   | 2022-03-01T13:54:12.013+00:00              | 1     |
            | filter by history date     | filter[historyDate.lte]   | 2022-02-28T23:59:59+00:00                  | 1     |
            | filter by history date     | filter[historyDate.range] | 2022-02-01T00:00:00+00:00,2022-02-28T23:59:59+00:00 | 1 |
            | filter by history relation | filter[historyRelation]   | cd16cc1f-3abb-4625-bb96-fbe80dbe23e3      | 2     |

    # The change record of WMS1 does differ from its predecessor, so `delta_size__gt` finds it and a
    # threshold above any diff size finds nothing. The creation record has no predecessor at all,
    # which is what `delta` counts. The boolean filters answer with the unfiltered queryset for
    # false, which is what their help text promises.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                          | param                      | value | count |
            | filter rows without predecessor | filter[delta]              | None  | 1     |
            | filter rows with changed fields | filter[delta_size__gt]     | 0     | 1     |
            | filter rows with changed fields | filter[delta_size__gt]     | 99    | 0     |
            | filter created or changed rows  | filter[changed_or_created] | true  | 2     |
            | filter created or changed rows  | filter[changed_or_created] | false | 2     |
            | filter deleted or changed rows  | filter[changed_or_deleted] | true  | 1     |
            | filter deleted or changed rows  | filter[changed_or_deleted] | false | 2     |

    # The frontend lists a changelog newest first, so the order of the history date is asserted and
    # not only that the request was answered.
    Scenario Outline: Can sort the history by its date
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering     | first                                |
            | historyDate  | 639cb553-8c30-4e72-a38d-10351ce81cf1 |
            | -historyDate | 40d6bddd-6e8b-4487-b3ed-ee2a4ac5dee2 |

