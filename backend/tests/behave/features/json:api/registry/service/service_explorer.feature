@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_wms.json @fixtures:test_wfs.json
Feature: Spatial service discovery
    Curators can discover services by map area without loading their elements.

    Scenario Outline: Request service coverage and filter by viewport
        Given I use the endpoint http://localhost:8000/api/registry/<endpoint>
        Given I set a queryparam "fields[<resource>]" with value "id,title,extent,element_count,can_edit"
        Given I set a queryparam "filter[bboxLatLon.intersects]" with value "POLYGON((-180 -90,180 -90,180 90,-180 90,-180 -90))"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"
        Then I expect that response json has an attribute "data.[0].attributes.elementCount"
        Then I expect that response json has an attribute "data.[0].attributes.extent.type"

        Examples:
            | endpoint | resource          |
            | wms      | WebMapService     |
            | wfs      | WebFeatureService |
