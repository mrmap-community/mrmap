@fixtures:test_wms.json @fixtures:test_keywords.json
Feature: OperationalIncident List Endpoint
    As an authenticated member of a deployment,
    I want to read the operational incidents I am permitted to see,
    so that I learn which problems stand for my resources without reading server logs.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/notify/operational-incidents

    # The endpoint answers incidents about resources and about the deployment
    # itself. None of it is for an anonymous client - not a list, not a count,
    # not the answer behind a detail url (#1319).
    Scenario: An anonymous client reads nothing
        Given I am an anonymous user
        When I send the request with GET method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    # The one permission rule: an authenticated user reads the incidents of
    # the resources he may view - and no others. User1 of the users fixture
    # holds no view permission, so the standing incidents of the WMS and of
    # the deployment are both invisible to him.
    Scenario: A user without any view permission reads an empty history
        Given an incident "monitoring_did_not_answer" stands for the WMS of the feature
        And a system incident "queue_without_consumer" stands
        And I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "0"

    # Existence itself is protected: the detail of an incident the caller may
    # not view answers like an incident that was never reported - a 404, not
    # a 403 that would confirm the incident behind the url (#1319).
    Scenario: An incident the caller may not view answers as if it were not there
        Given an incident "monitoring_did_not_answer" stands for the WMS of the feature and its detail is requested
        And I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 404
        Then I expect that response json has an attribute "errors.[0].code" with value "not_found"

    # The owner of the service reads the incident standing for it. The
    # payload is the contract of #1321: lifecycle, severity, the affected
    # resource as type and id and the bounded details - and no dedup key,
    # which is the reporters' internal identity.
    Scenario: The permitted user reads the incident of his service
        Given the user "User2" may view the WMS of the feature
        And an incident "monitoring_did_not_answer" stands for the WMS of the feature
        And I am logged in as User2 with password User2
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"
        Then I expect that response json has an attribute "data.[0].attributes.code" with value "monitoring_did_not_answer"
        Then I expect that response json has an attribute "data.[0].attributes.severity" with value "warning"
        Then I expect that response json has an attribute "data.[0].attributes.status" with value "active"
        Then I expect that response json has an attribute "data.[0].attributes.scope" with value "resource"
        Then I expect that response json has an attribute "data.[0].attributes.affectedResource.type" with value "WebMapService"
        Then I expect that response json has an attribute "data.[0].attributes.affectedResource.id" with value "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
        Then I expect that response json does not have an attribute "data.[0].attributes.dedupKey"

    # A recurrence of a standing problem is not a second incident: the step
    # reports the same code twice through the reporter, which is exactly
    # what a retry of a task does; the list answers one row which counts
    # both.
    Scenario: A recurrence raises the count of the standing incident
        Given the user "User2" may view the WMS of the feature
        And an incident "harvest_stalled" stands for the WMS of the feature
        And an incident "harvest_stalled" stands for the WMS of the feature
        And I am logged in as User2 with password User2
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"
        Then I expect that response json has an attribute "data.[0].attributes.occurrenceCount" with value "2"

    # The queues of the notification center ask by the lifecycle; the
    # resolved history is inspectable and never mixed into the active view.
    Scenario Outline: Can <action>
        Given the user "User2" may view the WMS of the feature
        And an incident "monitoring_did_not_answer" stands for the WMS of the feature
        And an incident "update_did_not_finish" stands for the WMS and is resolved
        And I am logged in as User2 with password User2
        And I set a queryparam "<param>" with value "<value>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | action                            | param             | value    | count |
            | filter by the active lifecycle    | filter[status]    | active   | 1     |
            | filter by the resolved lifecycle  | filter[status]    | resolved | 1     |
            | filter by the warning severity    | filter[severity]  | warning  | 1     |
            | filter by the error severity      | filter[severity]  | error    | 1     |

    # The contextual screen of #1322 asks all incidents which stand for one
    # service; the read answers the service's own incidents and keeps the
    # system incident invisible to a non-superuser anyway.
    Scenario: Can filter incidents by the service they stand for
        Given the user "User2" may view the WMS of the feature
        And an incident "monitoring_did_not_answer" stands for the WMS of the feature
        And a system incident "queue_without_consumer" stands
        And I am logged in as User2 with password User2
        And I set a queryparam "filter[service]" with value "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "1"

    # A rejected parameter belongs to the contract: a field the incident does
    # not have is refused, not answered with everything.
    Scenario: Can't filter by a field the incident does not have
        Given I am logged in as User2 with password User2
        And I set a queryparam "filter[not_a_field]" with value "x"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"

    # The api is read-only for regular clients: an incident is decided by
    # its publishers, never by a client (#1319).
    Scenario: The list refuses a write
        Given I am logged in as User1 with password User1
        When I send the request with POST method
        Then I expect the response status is 405
