# GetRecordById over the mixed record set (#829, epic #824).
#
# The operation was pinned without a record body until #1006 (the builder
# dropped every document it was given) and the lookup asked the application
# table only since the union of #988; the Django pins are
# tests/django/test_csw_get_record_by_id.py and
# tests/django/test_searchable_application_records.py. What this feature adds
# is the operation on the mixed fixture set: an identifier of the catalogue is
# answered from whichever of the three record tables holds it, and the second
# MrMap of the epic's closure scenario can open the application records it
# just harvested by the identifier it received in GetRecords.
#
# The fixture set is the one of get_records_mixed_types.feature -- two dataset
# records (RBSN_RR, RBSN_RH), one service record (de.beispiel.dienst-1) and
# one application record (de.beispiel.anwendung-1), each answering its own
# stored document.
@fixtures:test_keywords.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json @fixtures:test_csw_mixed_records.json
Feature: MrMap CatalogueService GetRecordById Endpoint
    As an operator of a second MrMap instance,
    I want to open catalogue records of every kind by their identifier,
    so that the records of a harvest keep their stored document readable.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/csw

    Scenario: GetRecordById answers the stored document of an application record
        Given I set a queryparam "REQUEST" with value "GetRecordById"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "Id" with value "de.beispiel.anwendung-1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath "concat(count(//*[local-name()='GetRecordByIdResponse']/*), '')" with value "1"
        # the response root itself is named GetRecordByIdResponse, so the step's
        # root-relative ".//" would find no descendant of that name -- the
        # absolute path reads the root and the document child below it
        Then I expect that there is a xpath "//*[local-name()='GetRecordByIdResponse']/*[1]//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "de.beispiel.anwendung-1"

    # One Id list reaching two of the three record tables: the lookup is one
    # union, not three endpoints, and the response ships the documents of both
    # kinds side by side.
    Scenario: GetRecordById asks all three record tables for an identifier list
        Given I set a queryparam "REQUEST" with value "GetRecordById"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "Id" with value "de.beispiel.anwendung-1,de.dwd.geoserver.fach.RBSN_RR"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath "concat(count(//*[local-name()='GetRecordByIdResponse']/*), '')" with value "2"
        Then I expect that there is a xpath "concat(count(//*[local-name()='CharacterString'][text()='de.beispiel.anwendung-1']), '')" with value "1"
        Then I expect that there is a xpath "concat(count(//*[local-name()='CharacterString'][text()='de.dwd.geoserver.fach.RBSN_RR']), '')" with value "1"
