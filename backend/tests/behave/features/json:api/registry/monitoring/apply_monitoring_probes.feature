@fixtures:test_keywords.json @fixtures:test_wms.json
Feature: WebMapService Monitoring Probe Apply Endpoint
    As an API client,
    I want to apply monitoring probes I selected from the monitoring probe preview,
    so that they are persisted on my monitoring setting without ever duplicating.

    Background: Plain JSON endpoint, stored capabilities and a monitoring setting
        Given I use the endpoint http://localhost:8000/api/registry/wms/cd16cc1f-3abb-4625-bb96-fbe80dbe23e3/monitoring-probes
        And I set the header "HTTP_ACCEPT" with value "application/json"
        And I set the content type of the request to application/json
        And the WMS stores a capabilities document
        And a monitoring setting exists for the service
        And User1 has the model permission "registry.change_webmapservice"
        And User1 may change the service and the monitoring setting
        And I am logged in as User1 with password User1

    Scenario: Can apply selected candidates as service writer
        Given I fetch the monitoring probe preview for the service
        And I select the GetCapabilities probe and the GetMap probe of layer "node1.2" from the preview
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "summary.created" with value "2"
        And I expect that response json has an attribute "generatorVersion"
        And the setting has "1" generated GetCapabilities probes
        And the setting has "1" generated GetMap probes
        And the setting is not enabled

    Scenario: Applying the same candidates again never duplicates a probe
        Given I fetch the monitoring probe preview for the service
        And I select the GetCapabilities probe and the GetMap probe of layer "node1.2" from the preview
        When I send the request with POST method
        Then I expect the response status is 200
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "summary.unchanged" with value "2"
        And the setting has "1" generated GetCapabilities probes
        And the setting has "1" generated GetMap probes

    Scenario: A stale preview is refused and persists nothing
        Given an apply payload with a fabricated candidate
        When I send the request with POST method
        Then I expect the response status is 409
        And I expect that response json has an attribute "error" with value "stalePreview"
        And the setting has "0" generated GetCapabilities probes
        And the setting has "0" generated GetMap probes

    Scenario: Customized generated parameters survive a repeated apply
        Given I fetch the monitoring probe preview for the service
        And I select the GetCapabilities probe and the GetMap probe of layer "node1.2" from the preview
        And I send the request with POST method
        And the generated GetMap probe of layer "node1.2" is customized to width "77"
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "summary.preserved" with value "1"
        And the generated GetMap probe of layer "node1.2" still has width "77"

    Scenario Outline: Only a writer of service and setting may apply
        Given I fetch the monitoring probe preview for the service
        And I select the GetCapabilities probe and the GetMap probe of layer "node1.2" from the preview
        And I <actor>
        When I send the request with POST method
        Then I expect the response status is 403
        And I expect that response json has an attribute "detail"
        And the setting has "0" generated GetMap probes

        Examples:
            | actor                                    |
            | am an anonymous user                     |
            | am logged in as User2 with password User2 |
