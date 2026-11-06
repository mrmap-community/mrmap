@fixtures:test_keywords.json
Feature: Keyword List Endpoint
    As an API client,
    I want to sort the keywords by their display string,
    so that the pickers of the frontend can render them in order.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/keywords

    # The generic pickers of the frontend render resources with their
    # string_representation - for a keyword its text - and send exactly that
    # field as sort. Until the field entered the viewset's whitelist the
    # endpoint answered the request with a 400 and the picker stayed empty (#1035).
    Scenario Outline: Can sort keywords by their display string
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"

        Examples:
            | ordering              | first |
            | stringRepresentation  | 53    |
            | -stringRepresentation | 116   |

    # A rejected parameter belongs to the contract: a field the keyword does
    # not have stays answered with a bad request.
    Scenario: Can't sort by a field the keyword does not have
        Given I set a queryparam "sort" with value "not_a_field"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
