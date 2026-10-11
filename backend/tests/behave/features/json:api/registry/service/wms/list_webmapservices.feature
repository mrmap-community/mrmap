@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: WebMapService List Endpoint
    As an API client,
    I want to search for web map services,
    so that I can find relevant map content.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/wms

    Scenario: Can retrieve list as anonymous user
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"
        Then I expect that "17" queries where made

    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action             | param                      | value         | count |
            | search by title    | filter[search]             | WMS1          | 1     |
            | search by abstract | filter[search]             | wms1 abstract | 1     |
            | search by keywords | filter[search]             | meteorology   | 1     |
            | filter by title    | filter[title.icontains]    | WMS1          | 1     |
            | filter by abstract | filter[abstract.icontains] | wms1 abstract | 1     |

    # One row per filter class of WebMapServiceFilterSet. `exact` and `contains` are case sensitive
    # while `icontains` is not, which is why the lower case counterpart of a matching value is
    # listed next to it. The uuid of WMS1 is written in full because the resource ids of the
    # fixture are fixed and a filter that only "is answered" would not tell a broken lookup apart.
    # `is_update_candidate` is a BooleanFilter with lookup_expr isnull and exclude=True: true asks
    # for services a pending update job belongs to, false for the services without one.
    Scenario Outline: Can <action>
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                               | param                        | value                                        | count |
            | filter by exact title                | filter[title]                | WMS1                                         | 1     |
            | filter by exact title                | filter[title]                | wms1                                         | 0     |
            | filter by title contains             | filter[title.contains]       | MS1                                          | 1     |
            | filter by title contains             | filter[title.contains]       | wms                                          | 0     |
            | filter by id                         | filter[id]                   | cd16cc1f-3abb-4625-bb96-fbe80dbe23e3         | 1     |
            | filter by id contains                | filter[id.contains]          | cd16cc1f-3abb-4625-bb96-fbe80dbe23e3         | 1     |
            | filter by id icontains               | filter[id.icontains]         | CD16CC1F-3ABB-4625-BB96-FBE80DBE23E3         | 1     |
            | filter by id in                      | filter[id.in]                | cd16cc1f-3abb-4625-bb96-fbe80dbe23e3         | 1     |
            | filter by id in                      | filter[id.in]                | cd16cc1f-3abb-4625-bb96-fbe80dbe23e3,1b195589-dcfa-403f-9e66-e7e1c0a67024 | 2 |
            | filter services that may be updated  | filter[is_update_candidate]  | true                                         | 0     |
            | filter services that need no update  | filter[is_update_candidate]  | false                                        | 2     |

    # The uuid validators of django-filter run before the lookup is applied, so a partial uuid is
    # refused even for a lookup that would only search inside the stored value.
    Scenario Outline: Can't filter by an incomplete <param>
        Given I set a queryparam "<param>" with value "cd16cc1f"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"

        Examples:
            | param              |
            | filter[id.contains] |
            | filter[id]         |

    Scenario: Can't filter by a field the resource does not have
        Given I set a queryparam "filter[not_a_field]" with value "WMS1"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"

    # The filter value is a whole GeoJSON polygon; it stays on its own step instead of blowing the
    # examples table above up to 220 characters per row.
    Scenario: Can filter by bbox
        Given I set a queryparam "filter[bboxLatLon.contains]" with value "{'type': 'Polygon', 'coordinates': [[[7.062835693359375, 50.043911679834615], [7.568206787109375, 50.043911679834615], [7.568206787109375, 50.39451208023374], [7.062835693359375, 50.39451208023374], [7.062835693359375, 50.043911679834615]]]}"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    # Scenario: Can include layers
    #     Given I set a queryparam "include" with value "layers"
    #     When I send the request with GET method
    #     Then I expect the response status is 200
    #     Then I expect that response json has an attribute "included.[0].type" with value "Layer"
    #     Then I expect that "14" queries where made

    Scenario Outline: Can include <relation>
        Given I set a queryparam "include" with value "<relation>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].type" with value "<type>"

        Examples:
            | relation        | type                       |
            | keywords        | Keyword                    |
            | operationUrls   | WebMapServiceOperationUrl  |
            | serviceContact  | MetadataContact            |
            | metadataContact | MetadataContact            |
            | createdBy       | User                       |
            | lastModifiedBy  | User                       |
