@fixtures:test_keywords.json @fixtures:test_crs.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json @fixtures:test_applicationmetadata.json @fixtures:test_applicationharvesting.json
Feature: HarvestingJob Application Metadata Statistics
    As an API client,
    I want a harvesting run to answer its collected counts per record type,
    so that the application records it harvested are visible beside the dataset and service
    records.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/harvesting-jobs

    # The run of the fixture harvested: two application records as new, one of them again as
    # updated and again as existing and two as duplicated; beside them one new service record,
    # one new and one duplicated dataset record. The dataset and service counts answer as
    # before the application counts existed - the issue promises they stay untouched.
    Scenario: The run answers the application counts beside the untouched dataset and service counts
        Given I set a queryparam "filter[id]" with value "903"
        Given I set a queryparam "fields[HarvestingJob]" with value "id,new_application_metadata_count,updated_application_metadata_count,existing_application_metadata_count,duplicated_application_metadata_count,new_dataset_metadata_count,updated_dataset_metadata_count,existing_dataset_metadata_count,duplicated_dataset_metadata_count,new_service_metadata_count,updated_service_metadata_count,existing_service_metadata_count,duplicated_service_metadata_count"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.newApplicationMetadataCount" with value "2"
        Then I expect that response json has an attribute "data.[0].attributes.updatedApplicationMetadataCount" with value "1"
        Then I expect that response json has an attribute "data.[0].attributes.existingApplicationMetadataCount" with value "1"
        Then I expect that response json has an attribute "data.[0].attributes.duplicatedApplicationMetadataCount" with value "2"
        Then I expect that response json has an attribute "data.[0].attributes.newDatasetMetadataCount" with value "1"
        Then I expect that response json has an attribute "data.[0].attributes.updatedDatasetMetadataCount" with value "0"
        Then I expect that response json has an attribute "data.[0].attributes.existingDatasetMetadataCount" with value "0"
        Then I expect that response json has an attribute "data.[0].attributes.duplicatedDatasetMetadataCount" with value "1"
        Then I expect that response json has an attribute "data.[0].attributes.newServiceMetadataCount" with value "1"
        Then I expect that response json has an attribute "data.[0].attributes.updatedServiceMetadataCount" with value "0"
        Then I expect that response json has an attribute "data.[0].attributes.existingServiceMetadataCount" with value "0"
        Then I expect that response json has an attribute "data.[0].attributes.duplicatedServiceMetadataCount" with value "0"

    # A run which harvested no application record answers zero, not nothing: the sums CTE has
    # no row of that kind and Coalesce turns that into the number the api promises.
    Scenario: A run without application records answers zero applications
        Given I set a queryparam "filter[id]" with value "1"
        Given I set a queryparam "fields[HarvestingJob]" with value "id,new_application_metadata_count,duplicated_application_metadata_count"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "data.[0].attributes.newApplicationMetadataCount" with value "0"
        Then I expect that response json has an attribute "data.[0].attributes.duplicatedApplicationMetadataCount" with value "0"

    # The harvested records of a run are explorable as records of their own kind, as the
    # dataset and service ones are. The count counts the joined relation rows and not the
    # distinct records: the fixture's two records hang in six application relations of the
    # run, and the answer repeats a record per relation, as on the dataset endpoint.
    Scenario: The application records of a run are explorable as records
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/harvesting-jobs/903/harvested-application-metadata-records
        Given I set a queryparam "filter[harvested_application_metadata_relation__collecting_state]" with value "1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "6"

    Scenario Outline: The application records can be filtered by the collecting state of a run
        Given I use the endpoint http://localhost:8000/api/registry/application-metadata
        Given I set a queryparam "filter[harvested_application_metadata_relation__harvesting_job]" with value "903"
        Given I set a queryparam "filter[harvested_application_metadata_relation__collecting_state]" with value "<state>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "<count>"

        Examples:
            | state | count |
            | 1     | 6     |
            | 2     | 4     |
            | 4     | 0     |
