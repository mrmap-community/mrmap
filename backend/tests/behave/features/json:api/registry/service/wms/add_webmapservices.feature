@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: WebMapService Add Endpoint
    As an API client,
    I want to add web map services,
    so that I can manage them with Mr.Map.

    Background: Setup baseurl, content-type and payload
        Given I use the endpoint http://localhost:8000/api/registry/wms
        Given I set the content type of the request to application/vnd.api+json
        Given I mock the function "delay" of the module "registry.tasks.service.build_ogc_service" with return value as object
            """
            {
                "id": "62832ac8-692d-4a8b-b8d1-22cd22f7386c"
            }
            """
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "http://some-service.de?REQUEST=GetCapabilities&SERVICE=WMS&VERSION=1.3.0",
                        "collect_metadata_records": "true"
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "id": "1",
                                "type": "Organization"
                            }
                        }
                    }
                }
            }
            """

    Scenario: Can add as authenticated user
        Given I am logged in as User1 with password User1
        When I send the request with POST method
        Then I expect the response status is 202

    Scenario: Can't add as anonymous user
        Given I am an anonymous user
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: Wrong capabilities url
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "http://some-service.de?SERVICE=WMS&VERSION=1.3.0",
                        "collect_metadata_records": "true"
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "id": "1",
                                "type": "Organization"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400

    Scenario: Can add the endpoint as the service candidates answer hands it over
        # the service candidates of a metadata record answer the same endpoint
        # with the parameters the create serializer asks for, spelled as the
        # delivered document named them - this is the value the registration
        # form of the record is prefilled with
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows?service=WMS&version=1.3.0&request=GetCapabilities",
                        "collect_metadata_records": "true"
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "id": "1",
                                "type": "Organization"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 202
        # an add is taken as a task, so the answer names the queued task and not
        # a finished service
        Then I expect that response json has an attribute "data.attributes.taskName" with value "registry.tasks.service.build_ogc_service"
        Then I expect that response json has an attribute "data.attributes.status" with value "PENDING"

    Scenario: The capabilities path a record advertises bare is no get capabilities url
        # a record may advertise the endpoint as a plain path; this is why the
        # resolution hands over the qualified url above rather than this one
        Given I am logged in as User1 with password User1
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": "https://maps.dwd.de/geoserver/dwd/RBSN_RR/ows",
                        "collect_metadata_records": "true"
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "id": "1",
                                "type": "Organization"
                            }
                        }
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"


