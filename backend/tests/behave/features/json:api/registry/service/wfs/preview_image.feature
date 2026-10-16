@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_wfs.json
Feature: Automatic WFS image thumbnails
    Service details show a bounded feature sample without selecting a feature type.

    Background:
        Given I use the endpoint http://localhost:8000/api/registry/wfs/9cc4889d-0cd4-4c3b-8975-58de6d30db41/preview-image
        And I set the header "HTTP_ACCEPT" with value "image/png"
        And the registered WFS has an automatic image preview

    Scenario: Opening the preview renders sampled features as a PNG
        Given I am logged in as User1 with password User1
        When I send the request with GET method
        Then I expect the response status is 200
        And the WFS preview is a bounded PNG image
        And the WFS preview creates no update or harvesting jobs

    Scenario: Anonymous users without service permission cannot load the image
        Given I am an anonymous user
        When I send the request with GET method
        Then I expect the response status is 403
        And the WFS thumbnail has not contacted upstream
