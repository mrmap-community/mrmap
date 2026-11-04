"""Records whose stored xml_backup document cannot be served (#912).

A ``GetRecords`` answers the stored document of a matched record -- and the
document is a *file* of the media storage, only referenced by the record row.
When such a file is gone (the demo deployment lost most of its
``xml_documents`` tree in a storage incident; a quota hiccup or a failing disk
does the same on a healthy box), every query whose matched page contained one
of the records died with the raw FileNotFoundError of the document read:
``HTTP 500`` HTML for an otherwise valid query.

The refusal is an ``ows:ExceptionReport`` whose message names the record which
cannot be served (its own identifier, which is what a client pages by and an
operator restores by). A ``resultType=hits`` response is answered from the
counts alone and never reads a document -- those keep serving while records
with lost files stay in the catalogue, and that is pinned here as well.
"""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from lxml import etree

from registry.models.metadata import (DatasetMetadataRecord, MetadataContact)
from tests.django.test_csw_exception_reports import AssertsExceptionReport
from tests.django.test_csw_post_binding import gmd_document

GET_RECORDS = {
    "SERVICE": "CSW",
    "REQUEST": "GetRecords",
    "VERSION": "2.0.2",
}

GET_RECORD_BY_ID = {
    "SERVICE": "CSW",
    "REQUEST": "GetRecordById",
    "VERSION": "2.0.2",
}


class CswLostBackupDocumentTests(AssertsExceptionReport, TestCase):
    """The matched page of a query which contains a record it cannot serve."""

    def setUp(self):
        self.contact = MetadataContact.objects.create(name='lost backup contact')
        self.intact = [
            self.record('de.mrmap.intact-one'),
            self.record('de.mrmap.intact-two')]
        # the third record exists and is searchable, its file is not there
        self.lost = self.record('de.mrmap.file-gone')
        self.lost.xml_backup_file.delete()

    def record(self, identifier):
        return DatasetMetadataRecord.objects.create(
            metadata_contact=self.contact,
            dataset_contact=self.contact,
            code_space='de.mrmap.',
            code=identifier.split('.')[-1],
            file_identifier=identifier,
            title=identifier,
            xml_backup_file=SimpleUploadedFile(
                f'{identifier}.xml', gmd_document(identifier),
                content_type='application/xml'))

    def test_a_results_page_with_a_lost_document_is_refused_naming_it(self):
        response = self.client.get("/csw", {
            **GET_RECORDS, "resultType": "results", "maxRecords": "10"})

        self.assertExceptionReport(response, "NoApplicableCode")
        # the message has to carry the record -- the response of a whole page
        # dies with it, so the client and the operator must learn which record
        # the storage owes
        text = etree.fromstring(response.content).xpath(
            "//*[local-name()='Exception']/*[local-name()='ExceptionText']")[0]
        self.assertIn('de.mrmap.file-gone', text.text, response.content)

    def test_a_hits_response_never_reads_the_documents_and_still_answers(self):
        # Table 66: a hits response answers the size of the result set and no
        # record of it -- the lost file is nothing it touches, so the counts
        # keep serving while the record cannot ship its document
        response = self.client.get("/csw", {
            **GET_RECORDS, "resultType": "hits", "maxRecords": "10"})

        self.assertEqual(response.status_code, 200, response.content)

    def test_a_get_record_by_id_of_a_record_without_document_is_refused(self):
        response = self.client.get("/csw", {
            **GET_RECORD_BY_ID, "Id": "de.mrmap.file-gone"})

        self.assertExceptionReport(response, "NoApplicableCode")

    def test_an_unparsable_backup_document_is_refused_like_a_missing_one(self):
        # a file which is there but carries no document (empty, truncated by a
        # failed write) is the same failure of service from the client's view
        empty = self.record('de.mrmap.empty-file')
        empty.xml_backup_file = SimpleUploadedFile(
            'empty.xml', b"", content_type='application/xml')
        empty.save()

        response = self.client.get("/csw", {
            **GET_RECORDS, "resultType": "results", "maxRecords": "100"})

        self.assertExceptionReport(response, "NoApplicableCode")
