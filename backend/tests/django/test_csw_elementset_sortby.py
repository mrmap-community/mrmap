"""The element sets and the sorting of a ``GetRecords`` (#911).

Three conformance obligations of OGC 07-006r1, answered around the records of a
``GetRecords`` response:

* the ``elementSet`` attribute of Table 66 -- ``SearchResults`` names the element
  set it answers with, and it names it as ``elementSet``, the attribute the
  ``SearchResultsType`` of CSW-discovery.xsd declares (the misnamed
  ``elementSetName`` no response may carry);
* the element sets of 10.8.4.9 and Table 65 -- ``brief``, ``summary`` and ``full``
  answer the record views of the profile (see ``csw/elementsets.py`` for the
  mapping of the DCMI views onto 19139), a request which names none asks the
  default ``summary``, and a fourth value is refused with
  ``InvalidParameterValue`` locator ``ElementSetName``;
* ``ogc:SortBy`` of 10.8.4.9 -- the requested property orders the merged result
  set, ascending or descending, over both record tables and across the paging,
  and a property the catalogue does not sort on is refused with
  ``InvalidParameterValue``.

The paging attributes themselves are pinned by ``test_csw_get_records_response.py``
(#913) and the queryables by ``test_csw_queryables.py``; this module pins the
element set and the order of the records those pages answer.
"""

import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from lxml import etree

from csw.elementsets import DEFAULT_ELEMENT_SET, project_gmd_record
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      ServiceMetadataRecord)
from registry.ows_lib.csw.builder import CSWBuilder
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

CSW = {'csw': NAMESPACE_LOOKUP['csw_2_0_2']}
GMD = {'gmd': NAMESPACE_LOOKUP['gmd'], 'gco': NAMESPACE_LOOKUP['gco']}
OWS = {'ows': NAMESPACE_LOOKUP['ows']}

GET_RECORDS = {
    'SERVICE': 'CSW',
    'REQUEST': 'GetRecords',
    'VERSION': '2.0.2',
}

SEARCH_RESULTS = '/csw:GetRecordsResponse/csw:SearchResults'
FILE_IDENTIFIERS = '//gmd:fileIdentifier/gco:CharacterString/text()'
EXCEPTION_CODE = ('/ows:ExceptionReport/ows:Exception/@exceptionCode')
EXCEPTION_LOCATOR = '/ows:ExceptionReport/ows:Exception/@locator'


def gmd_document(identifier: str, title: str, abstract: str) -> bytes:
    """A gmd:MD_Metadata document carrying one element of every view (and some
    which only the full view keeps): the citation with a detail only it keeps,
    the abstract, keywords and extent of the identification, a contact and a
    distribution which no named view keeps.
    """
    return (
        '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
        ' xmlns:gco="http://www.isotc211.org/2005/gco">'
        '<gmd:fileIdentifier>'
        f'<gco:CharacterString>{identifier}</gco:CharacterString>'
        '</gmd:fileIdentifier>'
        '<gmd:hierarchyLevel><gmd:MD_ScopeCode'
        ' codeListValue="dataset">dataset</gmd:MD_ScopeCode></gmd:hierarchyLevel>'
        '<gmd:dateStamp><gco:DateTime>2024-05-04T00:00:00</gco:DateTime>'
        '</gmd:dateStamp>'
        '<gmd:contact><gmd:MD_Contact>'
        '<gmd:contact><gmd:CI_ResponsibleParty>'
        '<gmd:individualName><gco:CharacterString>Full only'
        '</gco:CharacterString></gmd:individualName>'
        '</gmd:CI_ResponsibleParty></gmd:contact>'
        '</gmd:MD_Contact></gmd:contact>'
        '<gmd:identificationInfo><gmd:MD_DataIdentification>'
        '<gmd:citation><gmd:CI_Citation>'
        f'<gmd:title><gco:CharacterString>{title}</gco:CharacterString></gmd:title>'
        '<gmd:date><gco:Date>2024-05-03</gco:Date></gmd:date>'
        '<gmd:otherCitationDetails><gco:CharacterString>full only'
        '</gco:CharacterString></gmd:otherCitationDetails>'
        '</gmd:CI_Citation></gmd:citation>'
        f'<gmd:abstract><gco:CharacterString>{abstract}</gco:CharacterString>'
        '</gmd:abstract>'
        '<gmd:keyword><gco:CharacterString>Wasser</gco:CharacterString>'
        '</gmd:keyword>'
        '<gmd:extent><gmd:EX_Extent>'
        '<gmd:geographicElement><gmd:EX_GeographicBoundingBox>'
        '<gmd:northBoundLatitude><gco:Decimal>55.0</gco:Decimal>'
        '</gmd:northBoundLatitude>'
        '</gmd:EX_GeographicBoundingBox></gmd:geographicElement>'
        '</gmd:EX_Extent></gmd:extent>'
        '</gmd:MD_DataIdentification></gmd:identificationInfo>'
        '<gmd:distributionInfo><gmd:MD_Distribution>'
        '<gmd:distributor><gco:CharacterString>full only</gco:CharacterString>'
        '</gmd:distributor>'
        '</gmd:MD_Distribution></gmd:distributionInfo>'
        '</gmd:MD_Metadata>'
    ).encode('utf-8')


class CswElementSetResponseTests(TestCase):
    """Table 66 and 10.8.4.9: which element set a response answers, and named how."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='CSW elementset contact')
        cls.record('one', 'Erste', 'abstract one')
        cls.record('two', 'Zweite', 'abstract two')

    @classmethod
    def record(cls, identifier, title, abstract):
        return DatasetMetadataRecord.objects.create(
            metadata_contact=cls.contact,
            dataset_contact=cls.contact,
            title=title,
            code_space='de.mrmap.',
            code=identifier,
            file_identifier=f'de.mrmap.{identifier}',
            xml_backup_file=SimpleUploadedFile(
                f'{identifier}.xml', gmd_document(identifier, title, abstract),
                content_type='application/xml'))

    def get_records(self, **query_params):
        response = self.client.get('/csw', {**GET_RECORDS, **query_params})
        self.assertEqual(response.status_code, 200, response.content)
        return etree.fromstring(response.content)

    def search_results(self, **query_params):
        return self.get_records(**query_params).xpath(
            SEARCH_RESULTS, namespaces=CSW)[0]

    def count_in_records(self, root, local_name):
        return len(root.xpath(
            f'{SEARCH_RESULTS}//*[local-name()="{local_name}"]',
            namespaces=CSW))

    def test_the_attribute_is_element_set_and_defaults_to_the_summary_view(self):
        # Table 65: a request which names no ElementSetName asks the default of
        # CSW-discovery.xsd, summary; Table 66: the response names that set as
        # elementSet -- the elementSetName attribute of the old response named a
        # request parameter instead and made every response invalid against the
        # schema it self-declares.
        search_results = self.search_results(resultType='results')
        self.assertEqual('summary', search_results.get('elementSet'))
        self.assertIsNone(search_results.get('elementSetName'))
        # and the set named is the set answered: the summary view abstract is
        # there, the elements only full keeps are not
        self.assertEqual(2, self.count_in_records(search_results.getroottree().getroot(), 'abstract'))

    def test_brief_answers_the_brief_view_and_no_abstract(self):
        # record.xsd BriefRecordType: dc:identifier, dc:title, dc:type, the
        # bounding box -- no subject and no abstract, which is what the live
        # audit of #911 answered wrong with the whole full document
        root = self.get_records(resultType='results', elementsetname='brief')
        self.assertEqual(
            'brief', self.search_results(resultType='results',
                                         elementsetname='brief').get('elementSet'))
        self.assertEqual(2, len(root.xpath(FILE_IDENTIFIERS, namespaces=GMD)))
        self.assertEqual(2, len(root.xpath(
            '//gmd:citation//gmd:title/gco:CharacterString/text()',
            namespaces=GMD)))
        self.assertEqual(2, self.count_in_records(root, 'hierarchyLevel'))
        self.assertEqual(2, self.count_in_records(root, 'extent'))
        for pruned in ('abstract', 'keyword', 'contact', 'dateStamp',
                       'otherCitationDetails', 'distributionInfo'):
            with self.subTest(pruned):
                self.assertEqual(0, self.count_in_records(root, pruned))

    def test_summary_adds_the_abstract_of_the_identification(self):
        root = self.get_records(resultType='results', elementsetname='summary')
        self.assertEqual(2, self.count_in_records(root, 'abstract'))
        self.assertEqual(2, self.count_in_records(root, 'keyword'))
        self.assertEqual(2, self.count_in_records(root, 'dateStamp'))
        self.assertEqual(2, self.count_in_records(root, 'extent'))
        for pruned in ('contact', 'otherCitationDetails', 'distributionInfo'):
            with self.subTest(pruned):
                self.assertEqual(0, self.count_in_records(root, pruned))

    def test_full_answers_the_stored_document_as_it_is(self):
        root = self.get_records(resultType='results', elementsetname='full')
        self.assertEqual(
            'full', self.search_results(resultType='results',
                                        elementsetname='full').get('elementSet'))
        for kept in ('abstract', 'keyword', 'dateStamp',
                     'otherCitationDetails', 'distributionInfo', 'extent'):
            with self.subTest(kept):
                self.assertEqual(2, self.count_in_records(root, kept))
        # the top level contact of every record -- the fixture nests a second
        # contact element inside it, so a deep count would answer four
        self.assertEqual(2, len(root.xpath(
            f'{SEARCH_RESULTS}/gmd:MD_Metadata/gmd:contact',
            namespaces={**CSW, **GMD})))

    def test_the_element_set_of_a_hits_response_is_named_though_no_record_ships(self):
        search_results = self.search_results(
            resultType='hits', elementsetname='brief')
        self.assertEqual('brief', search_results.get('elementSet'))
        self.assertEqual([], list(search_results))

    def test_an_element_set_which_is_none_of_the_three_is_refused(self):
        # the live probe of #911: elementsetname=banana answered 200 and the
        # whole full record
        response = self.client.get('/csw', {
            **GET_RECORDS, 'resultType': 'results', 'elementsetname': 'banana'})
        self.assertEqual(400, response.status_code, response.content)
        root = etree.fromstring(response.content)
        self.assertEqual(
            ['InvalidParameterValue'],
            root.xpath(EXCEPTION_CODE, namespaces=OWS))
        self.assertEqual(
            ['ElementSetName'], root.xpath(EXCEPTION_LOCATOR, namespaces=OWS))

    def test_the_three_names_are_answered_whatever_case_their_client_chose(self):
        # the KVP values of the endpoint compare case-insensitively, as the
        # operation name does (Table 65 note a); the response answers the
        # enumeration's own spelling
        for name in ('FULL', 'Brief', 'summary'):
            with self.subTest(name):
                search_results = self.search_results(
                    resultType='hits', elementsetname=name)
                self.assertEqual(name.lower(), search_results.get('elementSet'))

    def test_the_default_element_set_of_the_module_and_of_the_specification_agree(self):
        # a guard against drifting the summary default of the endpoint away from
        # the ElementSetName/@default of CSW-discovery.xsd it copies
        self.assertEqual('summary', DEFAULT_ELEMENT_SET)
        self.assertEqual(
            'summary', self.search_results(resultType='hits').get('elementSet'))


class CswSortByTests(TestCase):
    """10.8.4.9: what a SortBy orders, across both record tables and both pages."""

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='CSW sort contact')
        cls.documents = {}
        # one service record between two dataset records, so that every expected
        # order below is an order of the MERGED set and not the order of one
        # source; the dates run against the titles, so a sort by one can not
        # pass for a sort by the other, and the case of Banana between apple and
        # cherry pins that text orders case-insensitively on both sides of the merge
        cls.record(DatasetMetadataRecord, 'apple', datetime.datetime(
            2024, 3, 3, tzinfo=datetime.timezone.utc))
        cls.record(DatasetMetadataRecord, 'cherry', datetime.datetime(
            2024, 1, 1, tzinfo=datetime.timezone.utc))
        cls.record(ServiceMetadataRecord, 'Banana', datetime.datetime(
            2024, 2, 2, tzinfo=datetime.timezone.utc))

    @classmethod
    def record(cls, model, title, date_stamp, file_identifier=None):
        file_identifier = file_identifier or f'de.mrmap.{title}'
        kwargs = dict(
            metadata_contact=cls.contact,
            title=title,
            date_stamp=date_stamp,
            code_space='de.mrmap.',
            code=title,
            file_identifier=file_identifier)
        if model is DatasetMetadataRecord:
            kwargs['dataset_contact'] = cls.contact
        created = model.objects.create(
            xml_backup_file=SimpleUploadedFile(
                f'{title}.xml',
                gmd_document(file_identifier, title, f'abstract {title}'),
                content_type='application/xml'),
            **kwargs)
        cls.documents[created.pk] = file_identifier
        return created

    def file_identifiers(self, **query_params):
        response = self.client.get('/csw', {**GET_RECORDS, **query_params})
        self.assertEqual(response.status_code, 200, response.content)
        return etree.fromstring(response.content).xpath(
            FILE_IDENTIFIERS, namespaces=GMD)

    def test_sortby_ascending_orders_the_merged_set_by_the_property(self):
        self.assertEqual(
            ['de.mrmap.apple', 'de.mrmap.Banana', 'de.mrmap.cherry'],
            self.file_identifiers(
                resultType='results', maxRecords='10', sortby='title:A'))

    def test_sortby_descending_reverses_it(self):
        self.assertEqual(
            ['de.mrmap.cherry', 'de.mrmap.Banana', 'de.mrmap.apple'],
            self.file_identifiers(
                resultType='results', maxRecords='10', sortby='title:D'))

    def test_a_sorted_page_is_a_page_of_the_sorted_merged_set(self):
        # the second page of the sorted set is Banana -- the service record,
        # which no page of either source alone answers in the middle
        for position, expected in ((1, 'apple'), (2, 'Banana'), (3, 'cherry')):
            with self.subTest(position):
                self.assertEqual(
                    [f'de.mrmap.{expected}'],
                    self.file_identifiers(
                        resultType='results', maxRecords='1',
                        startPosition=str(position), sortby='title:A'))

    def test_sortby_orders_a_date_property_too(self):
        self.assertEqual(
            ['de.mrmap.cherry', 'de.mrmap.Banana', 'de.mrmap.apple'],
            self.file_identifiers(
                resultType='results', maxRecords='10', sortby='date:A'))
        self.assertEqual(
            ['de.mrmap.apple', 'de.mrmap.Banana', 'de.mrmap.cherry'],
            self.file_identifiers(
                resultType='results', maxRecords='10', sortby='modified:D'))

    def test_sort_properties_apply_in_the_order_the_request_names_them(self):
        # a second record shares the service records title, so only the second
        # property of the request can tell the pair apart: within the tie of
        # title, modified:D answers the February record before the January one
        self.record(DatasetMetadataRecord, 'Banana', datetime.datetime(
            2024, 1, 2, tzinfo=datetime.timezone.utc),
            file_identifier='de.mrmap.banana2')
        self.assertEqual(
            ['de.mrmap.Banana', 'de.mrmap.banana2'],
            self.file_identifiers(
                resultType='results', maxRecords='2', startPosition='2',
                sortby='title:A,modified:D'))

    def test_a_property_which_names_no_queryable_is_refused(self):
        response = self.client.get('/csw', {
            **GET_RECORDS, 'resultType': 'results', 'sortby': 'banana:A'})
        self.assertEqual(400, response.status_code, response.content)
        root = etree.fromstring(response.content)
        self.assertEqual(
            ['InvalidParameterValue'],
            root.xpath(EXCEPTION_CODE, namespaces=OWS))
        self.assertEqual(['SortBy'], root.xpath(EXCEPTION_LOCATOR, namespaces=OWS))

    def test_a_queryable_the_catalogue_does_not_sort_on_is_refused(self):
        # subject reaches a keyword over a relation, which would multiply the
        # records the sort orders -- 10.8.4.9 answers that refusal
        response = self.client.get('/csw', {
            **GET_RECORDS, 'resultType': 'results', 'sortby': 'subject:A'})
        self.assertEqual(400, response.status_code, response.content)
        root = etree.fromstring(response.content)
        self.assertEqual(
            ['InvalidParameterValue'],
            root.xpath(EXCEPTION_CODE, namespaces=OWS))

    def test_no_sortby_keeps_answering_the_primary_key_order(self):
        # the paging order test_csw_get_records_response.py pins unchanged: no
        # SortBy, the merged set of both sources ordered by the pk of a record
        self.assertEqual(
            [self.documents[pk] for pk in sorted(self.documents)],
            self.file_identifiers(resultType='results', maxRecords='10'))


class CswElementSetBuilderTests(SimpleTestCase):
    """Table 66 in the builder itself: the attribute a response carries."""

    def test_search_results_carries_element_set_not_element_set_name(self):
        root = CSWBuilder().build_get_records_response(
            total_records=0,
            records_returned=0,
            next_record=0,
            element_set='brief')
        search_results = root.xpath(SEARCH_RESULTS, namespaces=CSW)[0]
        self.assertEqual('brief', search_results.get('elementSet'))
        self.assertIsNone(search_results.get('elementSetName'))


class CswElementSetProjectionTests(SimpleTestCase):
    """The pruning of ``csw/elementsets.py`` on the documents themselves."""

    def project(self, document, element_set):
        return project_gmd_record(etree.fromstring(document), element_set)

    def test_a_container_which_keeps_nothing_is_dropped_not_answered_empty(self):
        # a document whose identification carries only an element no view keeps:
        # the identification itself must go with it, an empty
        # MD_DataIdentification is no valid 19139
        document = (
            '<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco">'
            '<gmd:identificationInfo><gmd:MD_DataIdentification>'
            '<gmd:purpose><gco:CharacterString>none of the views</gco:CharacterString>'
            '</gmd:purpose>'
            '</gmd:MD_DataIdentification></gmd:identificationInfo>'
            '</gmd:MD_Metadata>').encode('utf-8')
        root = self.project(document, 'brief')
        self.assertEqual([], list(root))

    def test_full_is_the_document_itself(self):
        document = gmd_document('id', 'title', 'abstract')
        root = self.project(document, 'full')
        self.assertEqual(
            1, len(root.xpath(
                '//gmd:distributionInfo', namespaces=GMD)))

    def test_the_kept_subtrees_are_kept_whole(self):
        # the view keeps the hierarchyLevel element and its MD_ScopeCode with the
        # codeListValue attribute, and the extent with its bounding box
        root = self.project(gmd_document('id', 'title', 'abstract'), 'brief')
        scope = root.xpath(
            '//gmd:hierarchyLevel/gmd:MD_ScopeCode', namespaces=GMD)[0]
        self.assertEqual('dataset', scope.get('codeListValue'))
        self.assertEqual(
            ['55.0'], root.xpath(
                '//gmd:extent//gmd:northBoundLatitude/gco:Decimal/text()',
                namespaces=GMD))

    def test_a_backup_wrapped_in_the_harvested_envelope_is_projected_inside_it(self):
        # harvested records store the response they arrived in as their backup
        # (see the RBSN fixtures of the behave suite): the envelope stands and
        # the MD_Metadata inside it is the document the view prunes
        envelope = (
            '<GetRecordsResponse xmlns="http://www.opengis.net/cat/csw/2.0.2"'
            ' xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco">'
            '<SearchStatus/><SearchResults>'
            + gmd_document('id', 'title', 'abstract').decode('utf-8')
            + '</SearchResults></GetRecordsResponse>').encode('utf-8')
        root = self.project(envelope, 'brief')
        self.assertEqual(
            ['GetRecordsResponse'], [etree.QName(root).localname])
        self.assertEqual(
            ['id'], root.xpath(
                '//gmd:fileIdentifier/gco:CharacterString/text()', namespaces=GMD))
        self.assertEqual([], root.xpath('//gmd:abstract', namespaces=GMD))
