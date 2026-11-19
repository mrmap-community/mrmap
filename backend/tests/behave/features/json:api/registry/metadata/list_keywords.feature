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
    #
    # The examples name the expected keyword by its display string. A keyword has
    # no natural id on the wire: its "id" is the surrogate key whichever loaddata
    # gave it first, so the number shifts with the fixtures a run happens to
    # load. The two cells used to hold "53" and "116", measured on the full run;
    # the T2 tier of the metadata area alone answers "55" and "118" for the same
    # rows, which made the documented tier red on every metadata run while the T3
    # run CI executes stayed green (#1640).
    #
    # The two strings are the bounds of test_keywords.json as the test database
    # orders them: digits sort before letters, so "10 m über Grund" opens the
    # ascending list, and the collation puts the lowercase text after the
    # uppercase, so the lowercase tail of the weather vocabulary opens the
    # descending one. A fixture which changes its bounds changes these cells.
    Scenario Outline: Can sort keywords by their display string
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.stringRepresentation" with value "<first>"

        Examples:
            | ordering              | first            |
            | stringRepresentation  | 10 m über Grund  |
            | -stringRepresentation | strenger Frost   |

    # A rejected parameter belongs to the contract: a field the keyword does
    # not have stays answered with a bad request.
    Scenario: Can't sort by a field the keyword does not have
        Given I set a queryparam "sort" with value "not_a_field"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
