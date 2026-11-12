"""The ``GetCapabilities`` KeywordList counts records of all three kinds (#829).

The capabilities document of the catalogue ranks its keywords by usage: the
view aggregates one grouped count per keyword LINK TABLE -- dataset, service
and application -- sums them per keyword and answers the ten most used ones as
the ``KeywordList`` of the document. Before #829 that was exactly two tables,
so a keyword which only application records carried was invisible in the
ranking no matter how often it was used, and a keyword shared across the kinds
was counted short by its application uses.

These tests pin both halves of the acceptance at the endpoint: a keyword the
application records alone carry enters the list, and the application table
contributes to the usage a shared keyword ranks with -- up to the point where
that contribution is the difference between making the ten and missing them.
The document itself (sections, negotiation) is ``test_csw_version_negotiation.py``;
how the builder merges these keywords with the persisted ones of the CSW
service is ``tests/django/registry/ows_lib/tests_builder.py``.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from lxml import etree

from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, Keyword,
                                      MetadataContact, ServiceMetadataRecord)
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

GET_CAPABILITIES = {
    'SERVICE': 'CSW',
    'REQUEST': 'GetCapabilities',
}

KEYWORDS = ('/csw:Capabilities/ows:ServiceIdentification'
            '/ows:Keywords/ows:Keyword/text()')

NSMAP = {'csw': NAMESPACE_LOOKUP['csw_2_0_2'],
         'ows': NAMESPACE_LOOKUP['ows']}


class CswCapabilitiesKeywordUsageTests(TestCase):
    """The usage ranking the capabilities document answers over all three tables."""

    def setUp(self):
        self.contact = MetadataContact.objects.create(
            name='CSW capabilities keyword contact')

    def record(self, model, identifier, keywords=()):
        """A record carrying keywords -- the ranking only reads those links.

        No stored document is needed: the usage count aggregates the keyword
        link tables, so nothing of the record beyond its kind and its keywords
        takes part in the answer.
        """
        fields = {'dataset_contact': self.contact} \
            if model is DatasetMetadataRecord else \
            {'application_contact': self.contact} \
            if model is ApplicationMetadataRecord else {}
        record = model.objects.create(
            metadata_contact=self.contact,
            code_space='de.mrmap.',
            code=identifier,
            file_identifier=f'de.mrmap.{identifier}',
            xml_backup_file=SimpleUploadedFile(
                f'{identifier}.xml',
                b'<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"/>'),
            **fields)
        for keyword in keywords:
            record.keywords.add(
                Keyword.objects.get_or_create(keyword=keyword)[0])
        return record

    def answered_keywords(self):
        response = self.client.get('/csw', GET_CAPABILITIES)
        self.assertEqual(response.status_code, 200, response.content)
        return etree.fromstring(response.content).xpath(
            KEYWORDS, namespaces=NSMAP)

    def test_a_keyword_only_application_records_carry_is_answered(self):
        """A keyword no dataset and no service holds still makes the list.

        One application record is usage enough to be the most used keyword of
        a catalogue which otherwise carries none.
        """
        self.record(ApplicationMetadataRecord, 'anwendung',
                    keywords=['Nachnutzung'])

        self.assertIn('Nachnutzung', self.answered_keywords())

    def test_the_ranking_counts_application_uses_into_the_top_ten(self):
        """An application usage lifts its keyword over the top-ten boundary.

        Ten filler keywords are each used by one dataset record and created
        first, so on usage alone they fill the ten and equal usages keep their
        keyword id order. ``Anwendungsthema`` stands last of the eleven and is
        carried by two application records: with the application table counted
        it holds usage 2 and answers, with the table missing it would tie the
        fillers on 1 and lose its id-order slot to the earliest of them.
        """
        for position in range(1, 11):
            self.record(
                DatasetMetadataRecord, f'fuellung-{position}',
                keywords=[f'Fuellwort-{position}'])
        self.record(ApplicationMetadataRecord, 'anwendung-1',
                    keywords=['Anwendungsthema'])
        self.record(ApplicationMetadataRecord, 'anwendung-2',
                    keywords=['Anwendungsthema'])

        answered = self.answered_keywords()

        self.assertIn('Anwendungsthema', answered,
                      'the application usage did not reach the ranking')
        self.assertIn('Fuellwort-1', answered)
        self.assertNotIn(
            'Fuellwort-10', answered,
            'the keyword the application usage displaced is still answered')

    def test_the_usage_of_a_keyword_is_summed_over_all_three_tables(self):
        """A keyword shared by the kinds counts once per table it links.

        ``Gemeinsam`` links one record of each kind -- usage 3 -- and is
        created after ten once-used dataset fillers, so only the sum over all
        three tables carries it into the ten; counting the application link
        out -- what the two-table annotation of #829 replaced -- drops it to a
        tie it loses on id order.
        """
        for position in range(1, 11):
            self.record(
                DatasetMetadataRecord, f'fuellung-{position}',
                keywords=[f'Fuellwort-{position}'])
        self.record(DatasetMetadataRecord, 'alpha', keywords=['Gemeinsam'])
        self.record(ServiceMetadataRecord, 'gamma', keywords=['Gemeinsam'])
        self.record(ApplicationMetadataRecord, 'anwendung',
                    keywords=['Gemeinsam'])

        answered = self.answered_keywords()

        self.assertIn('Gemeinsam', answered,
                      'the application link of the keyword was not counted')
        self.assertNotIn('Fuellwort-10', answered)
