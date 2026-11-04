# Application metadata records through the /csw endpoint (#829, epic #824).
#
# A separate feature on purpose: get_records.feature counts exactly the two
# dataset records of its fixture, and every count in it would move if this
# feature's records joined its set. This feature loads that trio (keywords,
# catalogue services and the two dataset records) plus
# registry/fixtures/test_csw_mixed_records.json, which adds one service record
# (de.beispiel.dienst-1) and one application record (de.beispiel.anwendung-1)
# -- the answer of `type = 'application'` and the merged paging below are
# about those two rows and nothing else.
#
# The four records have fixed primary keys, and the endpoint answers a page in
# primary key order, so the merged stream is fully known here:
#   9e57... RBSN_RH (dataset) < c0ff... anwendung-1 (application)
#   < d8b5... RBSN_RR (dataset) < f4ac... dienst-1 (service).
# That order is what lets a page boundary cut through the union of the three
# record tables and the scenario still name the records it expects.
#
# The two records of the new fixture carry their stored document like the RBSN
# records do: the fixture names a path and tests/behave/environment.py attaches
# the document file after loaddata -- the response of GetRecords ships that
# document, so it must exist.
@fixtures:test_keywords.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json @fixtures:test_csw_mixed_records.json
Feature: MrMap CatalogueService Mixed Records Endpoint
    As an operator of a second MrMap instance,
    I want the /csw endpoint to answer dataset, service and application records together,
    so that one harvest collects all three kinds of record.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/csw

    # Table 66: the hits response names the size of the whole mixed result set
    # and ships no record of it. numberOfRecordsMatched counting all three
    # kinds is the union the harvesting client of #827 pages through.
    Scenario: GetRecords counts dataset, service and application records together
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "hits"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "4"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsReturned" with value "0"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@nextRecord" with value "0"
        Then I expect that there is a xpath "concat(count(//*[local-name()='SearchResults']/*), '')" with value "0"

    # The type queryable of the acceptance: the application kind selects the
    # application record alone.
    Scenario: GetRecords type filter answers only the application record
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "type = 'application'"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "1"
        Then I expect that there is a xpath "concat(count(//*[local-name()='SearchResults']/*), '')" with value "1"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/*[1]//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "de.beispiel.anwendung-1"

    # The two kinds which were answered before the application record arrived
    # keep answering exactly their own records -- the third source does not
    # leak into either count.
    Scenario: GetRecords type filter still answers the dataset records alone
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "type = 'dataset'"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "2"
        Then I expect that there is a xpath "concat(count(//*[local-name()='CharacterString'][text()='de.dwd.geoserver.fach.RBSN_RR']), '')" with value "1"
        Then I expect that there is a xpath "concat(count(//*[local-name()='CharacterString'][text()='de.dwd.geoserver.fach.RBSN_RH']), '')" with value "1"
        Then I expect that there is a xpath "concat(count(//*[local-name()='CharacterString'][text()='de.beispiel.anwendung-1']), '')" with value "0"

    Scenario: GetRecords type filter still answers the service record alone
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "type = 'service'"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "1"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/*[1]//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "de.beispiel.dienst-1"

    # The shape the harvesting client requests when it asks a remote MrMap for
    # all kinds at once: one OR over the three values of the type queryable,
    # matched by every record of the catalogue and paged as one stream.
    Scenario: GetRecords OR filter over all three kinds matches every record
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "type = 'dataset' OR type = 'service' OR type = 'application'"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "4"
        Then I expect that there is a xpath "concat(count(//*[local-name()='CharacterString'][text()='de.dwd.geoserver.fach.RBSN_RR']), '')" with value "1"
        Then I expect that there is a xpath "concat(count(//*[local-name()='CharacterString'][text()='de.dwd.geoserver.fach.RBSN_RH']), '')" with value "1"
        Then I expect that there is a xpath "concat(count(//*[local-name()='CharacterString'][text()='de.beispiel.anwendung-1']), '')" with value "1"
        Then I expect that there is a xpath "concat(count(//*[local-name()='CharacterString'][text()='de.beispiel.dienst-1']), '')" with value "1"

    # The page boundary of that stream runs through the merged sources: the
    # first page pairs a dataset with the application record, the second page
    # pairs the other dataset with the service record.
    Scenario: GetRecords pages the OR-filtered mixed stream in primary key order
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "type = 'dataset' OR type = 'service' OR type = 'application'"
        Given I set a queryparam "maxRecords" with value "2"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "4"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsReturned" with value "2"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@nextRecord" with value "3"
        # the stream's first record is the lowest primary key of the four and
        # the application record answers second -- the merge does not group by source
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/*[1]//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "de.dwd.geoserver.fach.RBSN_RH"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/*[2]//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "de.beispiel.anwendung-1"

        Given I set a queryparam "startPosition" with value "3"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "4"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsReturned" with value "2"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@nextRecord" with value "0"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/*[1]//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "de.dwd.geoserver.fach.RBSN_RR"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/*[2]//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "de.beispiel.dienst-1"
