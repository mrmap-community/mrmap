Feature: Services
  As an API client
  I want to control the filtering of resources
  so that only resources are part of the response that are matched by the given filter.

  Scenario: Accessing the services API endpoint without any search criteria will return all services
    Given an authorized session
    Given a request url http://localhost:8000/api/v1/registry/service/services/?ordering=title
    When the request sends GET
    Then the response status is OK
    And all services objects are returned
    And a paginated response is returned
    And response objects are ordered ascending by title
    And "accessible" key is part of the response

  Scenario: Only resources which has keyword, title, abstract or uuid like "WMS" is part of the response
    Given an authorized session
    Given a request url http://localhost:8000/api/v1/registry/service/services/?search=WMS&ordering=title
    When the request sends GET
    Then the response status is OK
    And 1 result(s) is(are) returned, with WMS as search criteria
    And a paginated response is returned
    And response objects are ordered ascending by title
    And "accessible" key is part of the response

  Scenario: Only resources in the given date range are part of the response.
    Given an authorized session
    Given a request url http://localhost:8000/api/v1/registry/service/services/?registration_min=2021-10-12&registration_max=2021-10-20&ordering=title
    When the request sends GET
    Then the response status is OK
    And 1 result(s) is(are) returned, between 2021-10-12 and 2021-10-20 as registration range criteria
    And a paginated response is returned
    And response objects are ordered ascending by title
    And "accessible" key is part of the response

  Scenario: Only resources in the given datestamp range are part of the response.
    Given an authorized session
    Given a request url http://localhost:8000/api/v1/registry/service/services/?datestamp_min=2021-10-20&datestamp_max=2021-10-23&ordering=title
    When the request sends GET
    Then the response status is OK
    And 0 result(s) is(are) returned, between 2021-10-20 and 2021-10-23 as datestamp range criteria
    And a paginated response is returned
    And response objects are ordered ascending by title
    And "accessible" key is part of the response

  Scenario: Only resources intersecting with a given Bounding Box are part of the response.
    Given an authorized session
    Given a request url http://localhost:8000/api/v1/registry/service/services/?bbox_0=1&bbox_1=2&bbox_2=3&bbox_3=4&ordering=title
    When the request sends GET
    Then the response status is OK
    And 2 result(s) is(are) returned, when BoundingBox [1, 1, 2, 2] intersects with services features
    And a paginated response is returned
    And response objects are ordered ascending by title
    And "accessible" key is part of the response
