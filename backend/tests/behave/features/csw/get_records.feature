# Not skipped anymore (#855). These scenarios were skipped since #837 because every
# GetRecords answered a 500: the query of a request which arrives as GET query parameters
# was built with the typeNames the client named, and `typeNames` is an optional parameter
# -- `" ".join(None)` raised "TypeError: can only join an iterable" before a response was
# ever built. An `AnyText` filter could not have answered either: it looked up a pattern
# over the tsvector of the searchable projection of the records, which postgres refuses
# with "function lower(tsvector) does not exist".
#
# Both are answered by the records themselves now (see csw/queryables.py): a filter is a
# tsquery over the vector column of a record, a wildcarded pattern is asked of the texts
# that vector is tokenized out of, and the data of a response is the document of a record.
#
# The refused requests below are answered with the ows:ExceptionReport of OWS Common
# (OGC 05-008, clause 8) at HTTP 400 since #908; before, an empty
# <ows:ServiceExceptionReport/> stood at HTTP 200 or a TypeError answered a 500 before
# a report was built (the scenarios' @skip carried the reason until then).
#
# The fixture of this feature answers two dataset metadata records and no service metadata
# record: "Niederschlag an RBSN Stationen" (de.dwd.geoserver.fach.RBSN_RR, keyword
# Niederschlag) and "Relative Feuchte an RBSN Stationen" (de.dwd.geoserver.fach.RBSN_RH,
# keyword Luftfeuchtigkeit). Both cover the same box over Germany and both documents are
# stored by tests/behave/environment.py.
@fixtures:test_keywords.json @fixtures:test_csw.json @fixtures:test_datasetmetadata.json
Feature: MrMap CatalogueService Endpoint
    As an API client,
    I want to retreive metadata records,
    so that I can consume them by the mrmap csw endpoint.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/csw

    # Table 66 (OGC 07-006r1): a hits response answers the size of the result set and no
    # record of it -- numberOfRecordsReturned 0 and nextRecord 0, where 0 in nextRecord
    # means "all records have been returned" and leaves the client nothing to page on
    # (#913; before, the numbers of the page the endpoint had fetched stood in the response
    # while no record was shipped with them).
    Scenario: GetRecords Hits response
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "hits"
        Given I set a queryparam "maxRecords" with value "1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "2"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsReturned" with value "0"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@nextRecord" with value "0"
        # the vocabulary's xpath step compares values of nodes, and a count is no node,
        # so concat turns the number of records shipped into the one string it can read
        # (libxml2 demands two arguments from concat, hence the empty one)
        Then I expect that there is a xpath "concat(count(//*[local-name()='SearchResults']/*), '')" with value "0"

    Scenario: GetRecords results response without filter
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "2"

    Scenario: GetRecords results response with cql filter
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "ResourceIdentifier LIKE '%de.dwd.geoserver.fach.RBSN_RR'"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "1"

    Scenario: GetRecords results response with wrong filter field
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "unknownfield LIKE '%de.dwd.geoserver.fach.RBSN_RR'"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidQuery"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "Constraint"

    Scenario: GetRecords answers an exception report for a constraint without language
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "Constraint" with value "AnyText = 'niederschlag'"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "MissingParameter"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "CONSTRAINTLANGUAGE"

    Scenario: GetRecords answers an exception report for a malformed CQL constraint
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "&&& not a cql expression &&&"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidParameterValue"

    # The refusals below name the parameter whose value this endpoint can not answer;
    # the scenario of the missing SERVICE and REQUEST parameters belongs to
    # get_capabilities.feature.
    Scenario: GetRecords results response with unsupported typeNames
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "typeNames" with value "csw:record"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "NotSupported"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "typeNames"

    Scenario: GetRecords results response with unsupported outputSchema
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "outputSchema" with value "http://www.opengis.net/cat/csw/2.0.2"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "NotSupported"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "outputSchema"

    # Table 65 of OGC 07-006r1 makes `version` a mandatory (One) parameter of the
    # KVP GetRecords with the fixed value of the version this catalogue profiles.
    # Both rows below answered a raw HTTP 500 (#910): the handler of a KVP
    # GetRecords asks the request XML, which builds a CSWBuilder of the requested
    # version, and the schema lookup behind that builder raises a ValueError for
    # every version but 2.0.2 -- a Python error where the exception model of the
    # specification wants a report.
    Scenario: GetRecords without a version is refused naming the parameter
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "hits"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath "/*[local-name()='ExceptionReport']/@version" with value "1.2.0"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "MissingParameter"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "version"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/*[local-name()='ExceptionText']/text()" with value "The version parameter is mandatory for GetRecords and must name one of 2.0.2."

    Scenario: GetRecords with a version this catalogue does not speak is refused
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "version" with value "1.0.0"
        Given I set a queryparam "resultType" with value "hits"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidParameterValue"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "version"
        # the text names both the refused value and the values this server speaks,
        # so a client which sent the wrong one can correct it
        Then I expect that there is a xpath ".//*[local-name()='Exception']/*[local-name()='ExceptionText']/text()" with value "Unsupported version: 1.0.0. This catalogue speaks 2.0.2."

    Scenario: GetRecords validate response is acknowledged
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "validate"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='Acknowledgement']"
        Then I expect that there is a xpath ".//*[local-name()='EchoedRequest']/*[local-name()='GetRecords']/@resultType" with value "validate"

    # This scenario used to send REQUEST=GetRecords beside an Id parameter --
    # it never reached the operation its name names. #909 makes it a real
    # GetRecordById probe: the operation which retrieves "the default
    # representation of catalogue records using their identifier" (10.9) used
    # to answer 200 with a childless response for every identifier; now the
    # stored document of the record names it in the response. The refusals of
    # the mandatory Id of Table 67 are pinned in operation_dispatch.feature,
    # the identifier-list shapes of the audit (comma separated, repeated id=
    # parameters) in tests/django/test_csw_get_record_by_id.py.
    Scenario: GetRecordById answers the stored document of the identifier
        Given I set a queryparam "REQUEST" with value "GetRecordById"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "Id" with value "de.dwd.geoserver.fach.RBSN_RR"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath "/*[local-name()='GetRecordByIdResponse']/@version" with value "2.0.2"
        Then I expect that there is a xpath ".//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "de.dwd.geoserver.fach.RBSN_RR"

    # AnyText is the searchable representation of a record: a word of its title, its
    # abstract, its identifiers or one of its keywords. A wildcarded AnyText cannot be a
    # lookup over that representation -- postgres compares a vector with a tsquery and has
    # no lower(tsvector) -- so the pattern is asked of the texts the vector is built from.
    Scenario Outline: Can search the records of the catalogue by <queryable>
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "hits"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "<constraint>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "<matched>"

        Examples: The queryables of the catalogue
            | queryable                              | constraint                                                            | matched |
            | a word of the title of a record        | AnyText = 'niederschlag'                                              | 1       |
            | a word of the abstract of both records | AnyText = 'synoptic'                                                  | 2       |
            | a word of a keyword of a record        | AnyText = 'luftfeuchtigkeit'                                          | 1       |
            | a pattern over the texts of a record   | AnyText LIKE '%Feuchte%'                                              | 1       |
            | a pattern over both titles             | AnyText LIKE '%RBSN%'                                                 | 2       |
            | a keyword of a record                  | subject = 'Niederschlag'                                              | 1       |
            | a part of a keyword of a record        | subject LIKE '%uchtig%'                                               | 1       |
            | the kind of a record                   | type = 'dataset'                                                      | 2       |
            | a kind no record has                   | type = 'service'                                                      | 0       |
            | the kind and a word narrow each other  | AnyText = 'niederschlag' AND type = 'service'                         | 0       |
            | the identifier of a record             | identifier = 'de.dwd.geoserver.fach.RBSN_RH'                          | 1       |
            | the resource identifier of a record    | ResourceIdentifier = 'https://registry.gdi-de.org/id/de.bund.dwd/de.dwd.geoserver.fach.RBSN_RR' | 1       |

    # The box of both records covers Germany (5.87 47.27 to 15.04 55.06), so the two
    # scenarios name the box and a box which is nowhere near it.
    Scenario: GetRecords answers the records inside a bounding box
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "hits"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "BBOX(coverage, 5.0, 46.0, 16.0, 56.0)"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "2"

    Scenario: GetRecords answers nothing for a bounding box beside the records
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "hits"
        Given I set a queryparam "CONSTRAINTLANGUAGE" with value "CQL_TEXT"
        Given I set a queryparam "Constraint" with value "BBOX(coverage, -10.0, 30.0, -5.0, 35.0)"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "0"

    # The response answers the two record tables as one result set, which is ordered by the
    # primary key of a record: the Feuchte record (9e57ada9-...) before the Niederschlag
    # record (d8b50d33-...). One row asks for one page of that order and names the record it
    # answers, so a page which is not stable -- a merged order which the two sources do not
    # share -- fails on its own row. The last row asks for the first page once more and has
    # to hear about the record it heard about before.
    Scenario Outline: GetRecords answers <page> of its results
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "maxRecords" with value "1"
        Given I set a queryparam "startPosition" with value "<startPosition>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "2"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsReturned" with value "1"
        Then I expect that there is a xpath ".//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "<fileIdentifier>"

        Examples: The pages of the two records
            | page              | startPosition | fileIdentifier               |
            | the first page    | 1             | de.dwd.geoserver.fach.RBSN_RH |
            | the second page   | 2             | de.dwd.geoserver.fach.RBSN_RR |
            | the first page a second time | 1    | de.dwd.geoserver.fach.RBSN_RH |

    # A page which begins behind the last record is still a page of the same result set: it
    # names the size of that set and answers no record of it. Paging is answered by both
    # sources at once, so this is where a slice which was taken without an order would show
    # a record it should not answer.
    Scenario: GetRecords answers no record for a page behind its results
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "maxRecords" with value "1"
        Given I set a queryparam "startPosition" with value "3"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "2"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsReturned" with value "0"

    # ElementSetName and SortBy, ignored by the endpoint until #911 (the view said
    # so itself: "TODO: HAndle ELEMENTSETNAME parameter"). Table 66 names the
    # attribute of SearchResults elementSet -- not elementSetName, which every
    # response of the endpoint carried and which made none of them valid against
    # the CSW-discovery.xsd they self-declare. The views themselves are the DCMI
    # record views of record.xsd mapped onto this profile's gmd:MD_Metadata;
    # brief has no abstract, summary adds it, and full answerss the stored
    # document as the fixtures of this feature store it.
    Scenario: GetRecords names the element set it answers by the default of Table 65
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "maxRecords" with value "1"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@elementSet" with value "summary"
        # the identifier of a record belongs to the summary view, so the paging
        # scenarios above keep answering it -- and the abstract is there too
        Then I expect that there is a xpath "concat(count(//*[local-name()='SearchResults']//*[local-name()='abstract']), '')" with value "1"

    Scenario Outline: GetRecords answers the <view> of its records
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "maxRecords" with value "1"
        Given I set a queryparam "elementsetname" with value "<elementSetName>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@elementSet" with value "<elementSetName>"
        Then I expect that there is a xpath "concat(count(//*[local-name()='SearchResults']//*[local-name()='fileIdentifier']), '')" with value "<fileIdentifiers>"
        Then I expect that there is a xpath "concat(count(//*[local-name()='SearchResults']//*[local-name()='abstract']), '')" with value "<abstracts>"
        Then I expect that there is a xpath "concat(count(//*[local-name()='SearchResults']//*[local-name()='contact']), '')" with value "<contacts>"

        Examples: the element sets of ElementSetType, on the first page
            | view    | elementSetName | fileIdentifiers | abstracts | contacts |
            | brief   | brief          | 1               | 0         | 0        |
            | summary | summary        | 1               | 1         | 0        |
            | full    | full           | 1               | 1         | 1        |

    Scenario: GetRecords refuses an element set which is none of the three
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "elementsetname" with value "banana"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidParameterValue"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "ElementSetName"

    Scenario Outline: GetRecords orders its results by <sortby>
        # the pk order of the endpoint answers the Feuchte record first (the
        # paging scenarios above); a sort by the title of the records orders the
        # merged set the other way -- Niederschlag (RBSN_RR) before Relative
        # Feuchte (RBSN_RH) -- which no page of either record table alone shows
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "maxRecords" with value "1"
        Given I set a queryparam "sortby" with value "<sortby>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/*[1]//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "<first>"

        Examples: ascending and descending over the fixture records
            | sortby   | first                          |
            | title:A  | de.dwd.geoserver.fach.RBSN_RR  |
            | title:D  | de.dwd.geoserver.fach.RBSN_RH  |
            | title    | de.dwd.geoserver.fach.RBSN_RR  |

    Scenario: GetRecords orders a sorted set page by page
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "maxRecords" with value "1"
        Given I set a queryparam "startPosition" with value "2"
        Given I set a queryparam "sortby" with value "title:A"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/@numberOfRecordsMatched" with value "2"
        Then I expect that there is a xpath ".//*[local-name()='SearchResults']/*[1]//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']/text()" with value "de.dwd.geoserver.fach.RBSN_RH"

    Scenario: GetRecords refuses a property it does not sort on
        Given I set a queryparam "REQUEST" with value "GetRecords"
        Given I set a queryparam "version" with value "2.0.2"
        Given I set a queryparam "service" with value "CSW"
        Given I set a queryparam "resultType" with value "results"
        Given I set a queryparam "sortby" with value "unknownfield:A"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@exceptionCode" with value "InvalidParameterValue"
        Then I expect that there is a xpath ".//*[local-name()='Exception']/@locator" with value "SortBy"
