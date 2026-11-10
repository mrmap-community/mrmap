@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json @fixtures:test_applicationmetadata.json
Feature: ApplicationMetadataRecord Change Permissions
    As an API client,
    I want to know which grant lets me change an application metadata record,
    so that the record type joins the permission matrix of #727 with the same answers the
    dataset and service records give.

    Background: Setup endpoint, content type and the change payload
        Given I use the endpoint http://localhost:8000/api/registry/application-metadata/a11c0000-0000-4000-8000-000000000001
        Given I set the content type of the request to application/vnd.api+json
        Given I set the request payload to:
            """
            {"data": {"type": "ApplicationMetadataRecord", "id": "a11c0000-0000-4000-8000-000000000001", "attributes": {"title": "Pinned Title"}}}
            """

    Scenario: May not change an application record without any permission
        Given a user "app-no-perm" without any service permissions exists
        Given I am logged in as app-no-perm with password app-no-perm
        When I send the request with PATCH method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the application record title in the database is "Anwendung Niederschlag"

    Scenario: May not change an application record granted to the user's group only
        # the same split answer as on the WMS above (#727): the object grant alone
        # does not pass has_permission
        Given a user "app-object-only" without any service permissions exists
        Given the user "app-object-only" is member of a group granted the application metadata record
        Given I am logged in as app-object-only with password app-object-only
        When I send the request with PATCH method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the application record title in the database is "Anwendung Niederschlag"

    Scenario: May not change an application record with the global permission alone
        Given a user "app-global-only" without any service permissions exists
        Given the user "app-global-only" holds the global permission to change application metadata records
        Given I am logged in as app-global-only with password app-global-only
        When I send the request with PATCH method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the application record title in the database is "Anwendung Niederschlag"

    Scenario: May change an application record with the global and the group object permission
        # the pair is what works, as it does on the service records - the grant shape
        # accounts/signals.py writes for an owning organization
        Given a user "app-both" without any service permissions exists
        Given the user "app-both" holds the global permission to change application metadata records
        Given the user "app-both" is member of a group granted the application metadata record
        Given I am logged in as app-both with password app-both
        When I send the request with PATCH method
        Then I expect the response status is 200
        Then the application record title in the database is "Pinned Title"
        Then the application record title change is reverted

    # Read visibility parity with the dataset record: an application record is seen
    # exactly as far as a dataset record is seen by the same actor - an anonymous
    # client reads both, and canEdit says false for both until the pair of grants
    # above is handed out. One scenario asks both endpoints so the comparison itself
    # is what fails when the new record type drifts from the old ones.
    Scenario: Anonymous reads of an application record answer like the dataset record
        Given I am an anonymous user
        Given I use the endpoint http://localhost:8000/api/registry/application-metadata/a11c0000-0000-4000-8000-000000000001
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.canEdit" with value "False"
        Given I use the endpoint http://localhost:8000/api/registry/dataset-metadata/d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.attributes.canEdit" with value "False"
