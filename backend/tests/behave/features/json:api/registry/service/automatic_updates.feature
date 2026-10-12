@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_wms.json @fixtures:test_wfs.json
Feature: Automatic service updates
    Additions and removals can be published when element identities are clear.
    A possible rename needs a reviewed mapping to preserve the existing object.

    Background:
        Given I am logged in as User1 with password User1
        And I set the content type of the request to application/vnd.api+json

    Scenario Outline: Publish additions without a review
        Given the <service> capabilities contain additions only
        When the automatic service update runs
        And I use the automatic service update job endpoint
        And I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.attributes.statusCode" with value "5"
        And the added service element is published with existing element IDs preserved

        Examples:
            | service |
            | WMS     |
            | WFS     |

    Scenario Outline: Publish removals without a review
        Given the <service> capabilities contain removals only
        When the automatic service update runs
        And I use the automatic service update job endpoint
        And I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.attributes.statusCode" with value "5"
        And the removed service element is deleted with remaining element IDs preserved

        Examples:
            | service |
            | WMS     |
            | WFS     |

    Scenario Outline: Review a possible rename and preserve its existing ID
        Given the <service> capabilities contain an identifier rename
        When the automatic service update runs
        And I use the automatic service update job endpoint
        And I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.attributes.statusCode" with value "2"
        And the service update awaits review without replacing existing elements
        Given I review the service element rename
        When I send the request with PATCH method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.attributes.isConfirmed" with value "true"
        When the automatic service update resumes
        And I use the automatic service update job endpoint
        And I send the request with GET method
        Then I expect the response status is 200
        And I expect that response json has an attribute "data.attributes.statusCode" with value "5"
        And the renamed service element retains its existing ID

        Examples:
            | service |
            | WMS     |
            | WFS     |
