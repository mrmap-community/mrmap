@no_fixtures
Feature: System administration endpoints are admin only
    As a deployment operator,
    I want the scheduler tables and the system info refused without an
    administrator session,
    so that no anonymous caller reads deployment internals and no plain
    account schedules Celery work (#1445).

    Scenario Outline: Anonymous reads are refused
        Given I am an anonymous user
        Given I use the endpoint <endpoint>
        When I send the request with GET method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

        Examples:
            | endpoint                                                  |
            | http://localhost:8000/api/system/crontabs                |
            | http://localhost:8000/api/system/periodic-tasks          |
            | http://localhost:8000/api/system/info                    |

    Scenario Outline: Anonymous writes are refused
        Given I am an anonymous user
        Given I use the endpoint <endpoint>
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": <type>,
                    "attributes": {
                        "name": "anonymously-scheduled",
                        "task": "registry.tasks.service.recover_registration_reference_work"
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

        Examples:
            | endpoint                                                  | type           |
            | http://localhost:8000/api/system/crontabs                | CrontabSchedule |
            | http://localhost:8000/api/system/periodic-tasks          | PeriodicTask    |
