@fixtures:test_crs.json @fixtures:test_wfs.json @fixtures:test_keywords.json
Feature: WebFeatureService Monitoring Probe Apply Endpoint
    As an API client,
    I want to apply monitoring probes I selected from the monitoring probe preview of my web feature service,
    so that the bounded probes of its feature types are persisted without ever duplicating.

    Background: Plain JSON endpoint, stored capabilities and a monitoring setting
        Given I use the endpoint http://localhost:8000/api/registry/wfs/9cc4889d-0cd4-4c3b-8975-58de6d30db41/monitoring-probes
        And I set the header "HTTP_ACCEPT" with value "application/json"
        And I set the content type of the request to application/json
        And the WFS stores a capabilities document
        And a monitoring setting exists for the service
        And User1 has the model permission "registry.change_webfeatureservice"
        And User1 may change the service and the monitoring setting
        And I am logged in as User1 with password User1

    Scenario: Can apply selected candidates as service writer
        Given I fetch the monitoring probe preview for the service
        And I select the GetCapabilities probe and the GetFeature probe of feature type "node2" from the preview
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "summary.created" with value "2"
        And I expect that response json has an attribute "generatorVersion"
        And the setting has "1" generated WfsGetCapabilities probes
        And the setting has "1" generated GetFeature probes
        And the setting is not enabled

    Scenario: Applying the same candidates again never duplicates a probe
        Given I fetch the monitoring probe preview for the service
        And I select the GetCapabilities probe and the GetFeature probe of feature type "node2" from the preview
        And I send the request with POST method
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "summary.unchanged" with value "2"
        And the setting has "1" generated WfsGetCapabilities probes
        And the setting has "1" generated GetFeature probes

    Scenario: The preview proposes one bounded GetFeature probe per active feature type
        Given I fetch the monitoring probe preview for the service
        Then the preview proposes "3" GetFeature probes
        And the proposed GetFeature request asks for "10" features at most
        And the preview skips the feature type "node4" as "inactive"

    Scenario: The preview names the WFS versions its generator can build requests for
        Given I fetch the monitoring probe preview for the service
        Then the preview offers the versions "1.1.0, 2.0.0, 2.0.2"

    Scenario: The comprehensive preset adds the DescribeFeatureType probe of a feature type
        Given the preview and the apply use the "comprehensive" preset
        And I fetch the monitoring probe preview for the service
        And I select the GetFeature and the DescribeFeatureType probe of feature type "node2" from the preview
        When I send the request with POST method
        Then I expect the response status is 200
        And I expect that response json has an attribute "summary.created" with value "2"
        And the setting has "1" generated GetFeature probes
        And the setting has "1" generated DescribeFeatureType probes
        And the preview proposes "3" DescribeFeatureType probes

    Scenario: A stale preview is refused and persists nothing
        Given an apply payload with a fabricated GetFeature candidate
        When I send the request with POST method
        Then I expect the response status is 409
        And I expect that response json has an attribute "error" with value "stalePreview"
        And the setting has "0" generated GetFeature probes

    Scenario: A probe type of another service kind is refused
        Given an apply payload with a fabricated GetMap candidate
        When I send the request with POST method
        Then I expect the response status is 400
        And I expect that response json has an attribute "error" with value "probeType"
        And the setting has "0" generated GetFeature probes

    Scenario Outline: Only a writer of service and setting may apply
        Given I fetch the monitoring probe preview for the service
        And I select the GetCapabilities probe and the GetFeature probe of feature type "node2" from the preview
        And I <actor>
        When I send the request with POST method
        Then I expect the response status is 403
        And I expect that response json has an attribute "detail"
        And the setting has "0" generated GetFeature probes

        Examples:
            | actor                                     |
            | am an anonymous user                      |
            | am logged in as User2 with password User2 |
