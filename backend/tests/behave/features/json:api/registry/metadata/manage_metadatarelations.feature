@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json @fixtures:test_csw_mixed_records.json
Feature: Metadata Relation Write Endpoint
    As an authorized curator,
    I want to declare and take back couplings between metadata records,
    so that a service record states which dataset it operates on.

    Background: Setup baseurl and content-type
        Given I use the endpoint http://localhost:8000/api/registry/metadata-relations
        Given I set the content type of the request to application/vnd.api+json

    Scenario: Can't declare as anonymous user
        Given I am an anonymous user
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MetadataRelation",
                    "relationships": {
                        "serviceMetadata": {"data": {"type": "ServiceMetadataRecord", "id": "f4ac83a9-3d1e-4b2f-9c6a-9f2e7d1c5b0a"}},
                        "datasetMetadata": {"data": {"type": "DatasetMetadataRecord", "id": "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"}}
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "not_authenticated"

    Scenario: Can't declare without the change permission over a coupled record
        # D11 of docs/metadata-identity.md: the write follows the record's
        # change permission, never a permission over the join row
        Given a user "relation-writer" without any service permissions exists
        Given I am logged in as relation-writer with password relation-writer
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MetadataRelation",
                    "relationships": {
                        "serviceMetadata": {"data": {"type": "ServiceMetadataRecord", "id": "f4ac83a9-3d1e-4b2f-9c6a-9f2e7d1c5b0a"}},
                        "datasetMetadata": {"data": {"type": "DatasetMetadataRecord", "id": "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"}}
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"

    Scenario: Can declare the pair once, idempotently, and take it back
        Given a curator "relation-curator" granted to couple the records exists
        Given I am logged in as relation-curator with password relation-curator
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MetadataRelation",
                    "relationships": {
                        "serviceMetadata": {"data": {"type": "ServiceMetadataRecord", "id": "f4ac83a9-3d1e-4b2f-9c6a-9f2e7d1c5b0a"}},
                        "datasetMetadata": {"data": {"type": "DatasetMetadataRecord", "id": "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"}}
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 201
        # every declaration is the curator's own kind: is_internal plus origin
        # EDITOR (4) - the kind a re-harvest never touches (D7.1)
        Then I expect that response json has an attribute "data.attributes.isInternal" with value "true"
        Then I expect that response json has an attribute "data.attributes.origin" with value "4"
        When I send the request with POST method
        Then I expect the response status is 201
        Then the pair relation is answered exactly once
        When I delete the declared pair relation
        Then I expect the response status is 204
        Then the declared pair relation is gone

    Scenario: The provenance of the row is not writable
        Given I am logged in as mrmap with password mrmap
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MetadataRelation",
                    "attributes": {"isInternal": false, "origin": 1},
                    "relationships": {
                        "serviceMetadata": {"data": {"type": "ServiceMetadataRecord", "id": "f4ac83a9-3d1e-4b2f-9c6a-9f2e7d1c5b0a"}},
                        "datasetMetadata": {"data": {"type": "DatasetMetadataRecord", "id": "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"}}
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].source.pointer"

    Scenario: A record naming no coupling partner declares nothing
        Given I am logged in as mrmap with password mrmap
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MetadataRelation",
                    "relationships": {
                        "datasetMetadata": {"data": {"type": "DatasetMetadataRecord", "id": "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"}}
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 400

    Scenario: A harvested coupling is not the endpoint's to take back
        # the relation rows of the fixture are CAPABILITIES evidence: the
        # document which declared them owns them, not the curator (D7)
        Given I use the endpoint http://localhost:8000/api/registry/metadata-relations/1
        Given I am logged in as mrmap with password mrmap
        When I send the request with DELETE method
        Then I expect the response status is 403
        Then I expect that response json has an attribute "errors.[0].code" with value "permission_denied"
        Then the harvested relation of the fixture is still standing

    Scenario: The pair of a record is one group, asked from either side
        # the terms the relations tab of a record screens its pair group with:
        # the screen's own column plus the OTHER record column. No relation of
        # the model fills an element beside both records, so that pair of terms
        # answers exactly the pair row - from the dataset's screen as well as
        # from the service's one (#985)
        Given a curator "relation-curator" granted to couple the records exists
        Given I am logged in as relation-curator with password relation-curator
        Given I set the request payload to:
            """
            {
                "data": {
                    "type": "MetadataRelation",
                    "relationships": {
                        "serviceMetadata": {"data": {"type": "ServiceMetadataRecord", "id": "f4ac83a9-3d1e-4b2f-9c6a-9f2e7d1c5b0a"}},
                        "datasetMetadata": {"data": {"type": "DatasetMetadataRecord", "id": "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"}}
                    }
                }
            }
            """
        When I send the request with POST method
        Then I expect the response status is 201
        Then I expect that response json has an attribute "data.attributes.isPublishable" with value "true"
        Given I set a queryparam "filter[dataset_metadata]" with value "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"
        Given I set a queryparam "filter[service_metadata__isnull]" with value "false"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].relationships.serviceMetadata.data.id" with value "f4ac83a9-3d1e-4b2f-9c6a-9f2e7d1c5b0a"
        When I clear the queryparams
        Given I set a queryparam "filter[service_metadata]" with value "f4ac83a9-3d1e-4b2f-9c6a-9f2e7d1c5b0a"
        Given I set a queryparam "filter[dataset_metadata__isnull]" with value "false"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].relationships.datasetMetadata.data.id" with value "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"
        When I clear the queryparams
        # the query the graph of the relations tab runs: every column it draws
        # travels as an include, with a sparse fieldset for the title it shows.
        # A pair row fills only the dataset column of them all, so the include
        # of the whole list answers exactly the partner record (#985)
        Given I set a queryparam "filter[dataset_metadata]" with value "d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4"
        Given I set a queryparam "filter[service_metadata__isnull]" with value "false"
        Given I set a queryparam "include" with value "layer,featureType,wms,wfs,csw,datasetMetadata"
        Given I set a queryparam "fields[DatasetMetadataRecord]" with value "title"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "included.[0].attributes.title" with value "Niederschlag an RBSN Stationen"
