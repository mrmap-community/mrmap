@fixtures:test_wms.json @fixtures:test_keywords.json @fixtures:test_allowed_wms_operation.json
Feature: Related AllowedWebMapServiceOperation for wms List Endpoint
    As an API client,
    I want to add new allowed operation configurations,
    so that I can secure services.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3/allowed-wms-operations

    Scenario: Can retrieve list as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "3"

    Scenario: Can't retrieve list as anonymous user
        Given I am an anonymous user
        When I send the request with GET method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: Filter access rules for a group
        Given I am logged in as User1 with password User1
        Given I set a queryparam "filter[access_group]" with value "1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "3"

    Scenario: User filter retains shared rules when no group memberships match
        Given I am logged in as User1 with password User1
        Given I set a queryparam "filter[access_user]" with value "00000000-0000-0000-0000-000000000000"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    # AllowedWebMapServiceOperationFilterSet declares the operations as a choice filter, the primary
    # key as NumberInFilter and the secured layers as uuid lookups. A NumberInFilter parses its value
    # into a list, so the text lookups it was given can not match and `contains` and `icontains` answer
    # with nothing. The first layer of the fixture belongs to two of the three rules, the second one to
    # all three.
    #
    # The same filterset declares `id__exact = NumberInFilter(field_name="pk", lookup_expr="exact")`,
    # which hands a list to a lookup that expects one number, so `filter[id.exact]` aborts the request
    # with `TypeError: int() argument must be ... not 'list'` and a 500 instead of a 400. That belongs
    # into registry/filters/security.py (the lookup needs a plain NumberFilter), not into a scenario
    # that claims a 500 is the contract:
    #
    # Scenario: Can filter by one id
    #     Given I am logged in as User1 with password User1
    #     Given I set a queryparam "filter[id.exact]" with value "1235"
    #     When I send the request with GET method
    #     Then I expect the response status is 200
    #     Then I expect that response json has an attribute "meta.pagination.count" with value "1"
    Scenario Outline: Can <action>
        Given I am logged in as User1 with password User1
        Given I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                            | param                           | value                                 | count |
            | filter by operation               | filter[operations.value]        | 20                                    | 3     |
            | filter by id contains             | filter[id.contains]             | 35                                    | 0     |
            | filter by id icontains            | filter[id.icontains]            | 1237                                  | 0     |
            | filter by id in                   | filter[id.in]                   | 1235,1236                             | 2     |
            | filter by description             | filter[description]             | with spatial restriction in koblenz   | 1     |
            | filter by description contains    | filter[description.contains]    | koblenz 2                             | 2     |
            | filter by secured layer           | filter[secured_layers.id]       | 16b93d90-6e2e-497a-b26d-cadbe60ab76e | 2     |
            | filter by secured layer           | filter[secured_layers.id]       | 226e655b-b6cd-48a4-95e2-8bfe1c933790 | 3     |

    # The group filter is a relation filter bound to the users of the deployment, so an unknown user
    # is refused instead of answering with an empty list. Only the hand written `access_user` filter
    # above falls back to the rules without any group.
    Scenario: Can't filter by a user that does not exist
        Given I am logged in as User1 with password User1
        Given I set a queryparam "filter[allowedGroups.user]" with value "00000000-0000-0000-0000-000000000000"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid_choice"

    # The spatial policy tester of the frontend lists the rules ordered by their id.
    Scenario Outline: Can sort the rules by their id
        Given I am logged in as User1 with password User1
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering | first |
            | id       | 1235  |
            | -id      | 1237  |
