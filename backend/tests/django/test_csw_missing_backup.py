"""Records whose stored xml_backup document cannot be served (#912, #1150).

A ``GetRecords`` answers the stored document of a matched record -- and the
document is a *file* of the media storage, only referenced by the record row.
When such a file is gone (#1150 measured ~10 % of the demo corpus missing,
spread uniformly over every import epoch; a quota hiccup or a failing disk
does the same on a healthy box), every query whose matched page contained one
of the records died with the raw FileNotFoundError of the document read:
``HTTP 500`` HTML for an otherwise valid query.

The refusal is an ``ows:ExceptionReport`` whose message names the record which
cannot be served (its own identifier, which is what a client pages by and an
operator restores by). #1150 fixed the two ways that refusal told more than it
may: it interpolates neither the OSError detail nor any storage path -- the
absolute media path is deployment-internal information and this endpoint
answers anonymous callers -- and it is answered 500, because a lost file is a
failure of the server's storage, not a faulty request. A ``resultType=hits``
response is answered from the counts alone and never reads a document -- those
keep serving while records with lost files stay in the catalogue, and that is
pinned here as well.
"""

from django.conf import settings
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

    def exception_text(self, response):
        return etree.fromstring(response.content).xpath(
            "//*[local-name()='Exception']/*[local-name()='ExceptionText']")[0].text

    def test_a_results_page_with_a_lost_document_is_refused_naming_it(self):
        response = self.client.get("/csw", {
            **GET_RECORDS, "resultType": "results", "maxRecords": "10"})

        # the storage owes the answer, not the request (#1150)
        self.assertExceptionReport(
            response, "NoApplicableCode", status=500)
        # the message has to carry the record -- the response of a whole page
        # dies with it, so the client and the operator must learn which record
        # the storage owes
        self.assertIn('de.mrmap.file-gone', self.exception_text(response),
                      response.content)

    def test_the_refusal_never_carries_a_storage_path(self):
        # #1150: the raw FileNotFoundError interpolated into the refusal
        # reported the absolute path of the media root to anonymous callers;
        # the detail belongs to the server log, the report names the record
        response = self.client.get("/csw", {
            **GET_RECORDS, "resultType": "results", "maxRecords": "10"})

        self.assertExceptionReport(
            response, "NoApplicableCode", status=500)
        text = self.exception_text(response)
        self.assertNotIn(settings.MEDIA_ROOT, text, response.content)
        self.assertNotIn('xml_documents', text, response.content)
        self.assertNotIn('md_metadata.xml', text, response.content)

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

        self.assertExceptionReport(
            response, "NoApplicableCode", status=500)

    def test_an_unparsable_backup_document_is_refused_like_a_missing_one(self):
        # a file which is there but carries no document (empty, truncated by a
        # failed write) is the same failure of service from the client's view
        empty = self.record('de.mrmap.empty-file')
        empty.xml_backup_file = SimpleUploadedFile(
            'empty.xml', b"", content_type='application/xml')
        empty.save()

        response = self.client.get("/csw", {
            **GET_RECORDS, "resultType": "results", "maxRecords": "100"})

        self.assertExceptionReport(
            response, "NoApplicableCode", status=500)
