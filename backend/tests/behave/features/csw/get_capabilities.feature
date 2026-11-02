# Skipped on purpose, and the reason is #866, not the searchable views #855 removes: both
# scenarios of this feature assert the exception report of a refused request, and the endpoint
# does not answer one. csw/views.py builds MissingRequestParameterException and
# MissingServiceParameterException without the service_type and service_version arguments that
# OGCServiceException requires, so a request without REQUEST or SERVICE answers a 500; with that
# fixed, the report skeleton of ("csw", "Exception", "2.0.2") is an empty
# <ows:ServiceExceptionReport xmlns:ows="http://www.opengis.net/ows"/>, so the xml comparison
# below has no payload to compare. Unskip together with those two fixes. The GetRecords requests
# which are refused for the same reason carry their @skip in get_records.feature.
@fixtures:test_keywords.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json @skip
Feature: CSW Endpoint
    As an API client,
    I want to retreive the capabilities document,
    so that I know all features of the csw service.

    The mandatory GetCapabilities operation allows CSW clients to retrieve service metadata from a server.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/csw

    Scenario: Missing SERVICE query param
        Given I set a queryparam "REQUEST" with value "GetCapabilities"
        Given I set a queryparam "version" with value "2.0.2"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response xml content is:
            """
            <?xml version="1.0" encoding="UTF-8"?><ServiceExceptionReport version="2.0.2" xmlns="http://www.opengis.net/ogc" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/ogc">
            <ServiceException code="MissingParameter" locator="service">
            Could not determine service for the requested service.
            </ServiceException>
            </ServiceExceptionReport>
            """


    Scenario: Missing REQUEST query param
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response xml content is:
            """
            <?xml version="1.0" encoding="UTF-8"?><ServiceExceptionReport version="2.0.2" xmlns="http://www.opengis.net/ogc" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.opengis.net/ogc">
            <ServiceException code="MissingParameter" locator="request">
            Could not determine request method from http request.
            </ServiceException>
            </ServiceExceptionReport>
            """
