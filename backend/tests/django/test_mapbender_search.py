"""The MapBender compatibility search, answered by the metadata records themselves.

``/mapbender/search`` is not the CSW endpoint: a MapBender client names its search words
as ``searchText`` and the kind of resource it wants as ``searchResources``, and the answer
is one JSON object per resource kind. Both are answered from the records now, through the
same querysets and the same vector a ``GetRecords`` searches (#855), which is what these
tests are about: the two branches of ``local_search`` and the values of an entry the
client renders.

The entry used to be built out of ``record.xml_backup`` -- the stored document of a record
-- which a record without a document answers as ``b""`` and which is bytes for every
record that has one; the values below are read from the record itself.
"""

import json

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import RequestFactory, TestCase

from mapbender_compatibility.views import MapBenderSearchApi
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, Keyword,
                                      MetadataContact, ServiceMetadataRecord)


class MapBenderSearchTest(TestCase):
    """The dataset, service and application branch of ``/mapbender/search``."""

    def setUp(self):
        self.contact = MetadataContact.objects.create(
            name='MapBender search contact')

        self.wasser = self.record(
            DatasetMetadataRecord, title='Wasserversorgung Hamburg',
            keywords=['Wasser'],
            bounding_geometry=MultiPolygon(Polygon.from_bbox(
                (5.0, 47.0, 10.0, 55.0))))
        self.boden = self.record(
            DatasetMetadataRecord, title='Bodenrichtwerte Kiel',
            keywords=['Bauen & Wohnen'])
        self.berlin = self.record(
            ServiceMetadataRecord, title='Wasserversorgung Berlin',
            keywords=['Wasser'])
        # the application record is found by words no dataset or service record
        # holds, so an application hit is always the application branch's doing
        self.anwendung = self.record(
            ApplicationMetadataRecord, title='Anwendung Wartung Dresden',
            keywords=['Anwendung'])

    def record(self, model, keywords=(), **fields):
        if model is DatasetMetadataRecord:
            # the dataset contact is the one invariant a dataset record has and a
            # service record does not
            fields.setdefault('dataset_contact', self.contact)
        elif model is ApplicationMetadataRecord:
            # ... and the application contact is the same invariant of an
            # application record
            fields.setdefault('application_contact', self.contact)
        record = model.objects.create(metadata_contact=self.contact, **fields)
        for keyword in keywords:
            # a keyword is a lookup row which every record carrying it shares (#817)
            record.keywords.add(
                Keyword.objects.get_or_create(keyword=keyword)[0])
        return record

    def search(self, **query_params):
        response = self.client.get('/mapbender/search', query_params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def entries(self, resources='dataset', **query_params):
        """The answer of a search, as the client reads it: ``md`` and ``srv``.

        The primary key of a record reaches the client as the string the JSON encoder
        answers it as.
        """
        content = self.search(searchResources=resources, **query_params)
        return content[resources]

    def test_the_dataset_branch_answers_the_dataset_records_a_word_matches(self):
        answer = self.entries(searchText='wasser')

        self.assertEqual(1, answer['md']['nresults'])
        [entry] = answer['srv']
        self.assertEqual(str(self.wasser.pk), entry['id'])
        self.assertEqual('Wasserversorgung Hamburg', entry['title'])
        self.assertEqual(self.contact.name, entry['respOrg'])
        self.assertEqual('5.0,47.0,10.0,55.0', entry['bbox'])

    def test_the_service_branch_answers_the_service_records_a_word_matches(self):
        answer = self.entries('service', searchText='wasser')

        self.assertEqual(1, answer['md']['nresults'])
        [entry] = answer['srv']
        self.assertEqual(str(self.berlin.pk), entry['id'])
        self.assertEqual('Wasserversorgung Berlin', entry['title'])

    def test_the_application_branch_answers_the_application_records(self):
        """``searchResources=application`` is a kind of record now, not an empty page.

        The record is found by a word of its title as well as by a word of its
        keyword -- both are words of its vector, the same vector a ``GetRecords``
        searches (#828).
        """
        for words in ('anwendung', 'wartung'):
            with self.subTest(searchText=words):
                answer = self.entries('application', searchText=words)

                self.assertEqual(1, answer['md']['nresults'])
                [entry] = answer['srv']
                self.assertEqual(str(self.anwendung.pk), entry['id'])
                self.assertEqual('Anwendung Wartung Dresden', entry['title'])
                self.assertEqual(self.contact.name, entry['respOrg'])

    def test_a_word_of_a_keyword_is_a_word_of_a_record(self):
        """The words of the keywords are in the vector of a record, not only its text."""
        answer = self.entries(searchText='wohnen')

        self.assertEqual(1, answer['md']['nresults'])
        self.assertEqual('Bodenrichtwerte Kiel', answer['srv'][0]['title'])

    def test_a_star_browses_instead_of_searching_for_nothing(self):
        """``searchText=*`` is the way a MapBender client asks for everything.

        An empty search is not a search which matches nothing, which is what the
        ``SearchQuery("")`` of the searchable projection answered: an empty tsquery, so
        the browse the MapBender widget sends on its first page was always empty.
        """
        self.assertEqual(2, self.entries()['md']['nresults'])
        self.assertEqual(2, self.entries(searchText='*')['md']['nresults'])

    def test_the_second_page_answers_the_next_record(self):
        """The pages of one kind of record, in the order of their primary keys."""
        order = list(DatasetMetadataRecord.objects.order_by('pk')
                     .values_list('pk', flat=True))

        first = self.entries(searchText='*', maxResults=1, searchPages=1)['srv']
        second = self.entries(searchText='*', maxResults=1, searchPages=2)['srv']

        self.assertEqual([str(order[0])], [entry['id'] for entry in first])
        self.assertEqual([str(order[1])], [entry['id'] for entry in second])
        self.assertEqual(
            2, self.entries(searchText='*', maxResults=1,
                            searchPages=2)['md']['nresults'],
            'a page names the size of the whole result set, not of itself')

    def test_a_record_without_a_stored_document_is_answered_as_well(self):
        """Nothing of a search answer reads the stored document of a record anymore."""
        self.assertEqual(b'', self.boden.xml_backup)
        self.assertEqual(1, self.entries(
            searchText='bodenrichtwerte')['md']['nresults'])

    def test_a_resource_kind_no_search_answers_answers_no_records(self):
        """``searchResources`` other than the kinds of a metadata record."""
        answer = self.entries('layer', searchText='wasser')

        self.assertEqual(0, answer['md']['nresults'])
        self.assertEqual([], answer['srv'])


class MapBenderCqlTest(TestCase):
    """The CQL filter the search forwards to the catalogue of ``catalogueId``.

    The filter is executed by a service the client names, not by this
    application, so a single quote of a search word closed the literal it was
    interpolated into and everything behind it became a predicate of the
    remote service. These tests are about the shape of the forwarded string
    (#1469), and a valid input is answered exactly as it was before.
    """

    def cql(self, **query_params):
        """The filter of a request, as ``remote_search`` would send it."""
        view = MapBenderSearchApi()
        view.request = RequestFactory().get('/mapbender/search', query_params)
        return view.build_cql_filter()

    def test_the_filter_of_an_ordinary_search_is_the_ordinary_filter(self):
        """The baseline the hardened filter must not move away from."""
        self.assertEqual(
            "Type LIKE 'dataset' And AnyText LIKE 'wald'"
            "AND BBOX(the_geom, 7.181,50.282,7.267,50.350)",
            self.cql(searchText='wald', searchBbox='7.181,50.282,7.267,50.350'))
        self.assertEqual(
            "Type LIKE 'service' And AnyText LIKE 'wald' And AnyText LIKE 'wasser'",
            self.cql(searchText='wald,wasser', searchResources='service'))

    def test_a_quote_of_a_search_word_is_doubled_inside_its_literal(self):
        """before: the quote closed the literal, so ``Or`` was parsed as CQL."""
        self.assertEqual(
            "Type LIKE 'dataset' And AnyText LIKE 'wald'' Or AnyText LIKE ''%'''",
            self.cql(searchText="wald' Or AnyText LIKE '%'"))

    def test_a_quote_of_the_resource_kind_is_doubled_inside_its_literal(self):
        self.assertEqual(
            "Type LIKE 'dataset'' Or 1=1--' And AnyText LIKE ''",
            self.cql(searchText='*', searchResources="dataset' Or 1=1--"))

    def test_a_bbox_of_four_coordinates_is_the_bbox_it_names(self):
        """Signed and fractional coordinates are coordinates, and a rejected
        bbox is no filter at all - a search is never widened by its own bbox."""
        for bbox in ('7.181,50.282,7.267,50.350', '-7.18,+50.28,7.26,50.35',
                     '.5,.6,7.2,50.3', ' 7.1 , 50.2 , 7.2 , 50.3 '):
            with self.subTest(searchBbox=bbox):
                self.assertEqual(
                    f"Type LIKE 'dataset' And AnyText LIKE ''"
                    f"AND BBOX(the_geom, {bbox})",
                    self.cql(searchText='*', searchBbox=bbox))

    def test_a_bbox_which_is_no_bbox_is_not_forwarded(self):
        """A predicate behind the coordinates is dropped with the coordinates."""
        for bbox in ("1,2,3,4) Or (1=1", '1,2,3', '1,2,3,4,5',
                     '1,2,3,4;DROP TABLE ows', 'a,b,c,d', '1,2,3,unknown'):
            with self.subTest(searchBbox=bbox):
                self.assertEqual(
                    "Type LIKE 'dataset' And AnyText LIKE 'wald'",
                    self.cql(searchText='wald', searchBbox=bbox))


class MapBenderEchoTest(TestCase):
    """The parameters the answer echoes back into its search filter.

    The MapBender widget writes the filter of the answer into its HTML, so a
    parameter with markup came back as markup of the page which rendered the
    answer (#1469).
    """

    def echo(self, **query_params):
        response = self.client.get('/mapbender/search', query_params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_the_answer_of_an_ordinary_request_echoes_its_parameters(self):
        """The baseline: an ordinary request is echoed as it was before."""
        answer = self.echo(searchText='wald', catalogueId='4', target='webclient')

        search_filter = answer['searchFilter']
        self.assertEqual(
            'searchText=wald&catalogueId=4&target=webclient',
            search_filter['origUrl'])
        self.assertEqual(
            'searchText=*&catalogueId=4&target=webclient',
            search_filter['searchText']['delLink'])
        self.assertEqual(
            'searchText=wald&catalogueId=4&target=webclient',
            search_filter['searchResources']['delLink'])
        self.assertEqual(
            'wald', search_filter['searchText']['item'][0]['title'])

    def test_markup_of_a_parameter_never_echoes_as_markup(self):
        payload = '<img src=x onerror=alert(1)>'

        answer = self.echo(searchText=payload, searchResources=payload)

        self.assertNotIn('<', response_body := json.dumps(answer))
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', response_body)
        # the search itself still runs over the words of the parameter, which
        # match no record - and the answer is keyed by the escaped kind
        escaped = payload.replace('<', '&lt;').replace('>', '&gt;')
        self.assertEqual(0, answer[escaped]['md']['nresults'])

    def test_a_quote_of_a_parameter_echoes_unchanged(self):
        """A quote is not markup - only the characters which open markup go."""
        answer = self.echo(searchText="wald'suche")

        self.assertEqual(
            "searchText=wald'suche", answer['searchFilter']['origUrl'])
