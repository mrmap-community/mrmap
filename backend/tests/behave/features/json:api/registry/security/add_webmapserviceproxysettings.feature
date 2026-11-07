@fixtures:test_keywords.json @fixtures:test_wms.json
Feature: WebMapServiceProxySetting Add Endpoint
    As an API client,
    I want to add the security proxy settings of a service,
    so that the proxy knows whether it camouflages and whether it logs the responses of that service.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/security/wms-proxy-settings
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapServiceProxySetting",
                    "attributes": {
                        "camouflage": true,
                        "logResponse": false
                    },
                    "relationships": {
                        "secured_service": {
                            "data": {
                                "id": "1b195589-dcfa-403f-9e66-e7e1c0a67024",
                                "type": "WebMapService"
                            }
                        }
                    }
                }
            }
            """

    Scenario: Can add as user with permissions
        Given I am logged in as mrmap with password mrmap
        When I send the request with POST method
        Then I expect the response status is 201

    Scenario: Can't add as anonymous user
        Given I am an anonymous user
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: Can't add as user without permissions
        Given I am logged in as User1 with password User1
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"

    # Responses may only be logged while the proxy camouflages, which the table refuses through the
    # check constraint `registry_webmapserviceproxysetting_log_response_without_camouflage`. Until
    # #1148 the pair was written and refused by PostgreSQL, whose CheckViolation is no DRF exception,
    # so this payload answered HTTP 500 and the constraint was an error path instead of an invariant.
    # The other service of the fixture is asked for, so the scenario does not ask for a setting the
    # scenario above may have written.
    Scenario: Can't log responses without camouflaging
        Given I am logged in as mrmap with password mrmap
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapServiceProxySetting",
                    "attributes": {
                        "camouflage": false,
                        "logResponse": true
                    },
                    "relationships": {
                        "secured_service": {
                            "data": {
                                "id": "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3",
                                "type": "WebMapService"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
        # the wording is Django's own: it names the constraint whose condition the pair violates,
        # which is what a client of the refused combination can act on
        Then I expect that response json has an attribute "errors.[0].detail" with value "Constraint “registry_webmapserviceproxysetting_log_response_without_camouflage” is violated."
