import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase
from django.test.utils import override_settings
from MrMap.settings import BASE_DIR
from registry.enums.harvesting import (LogKindEnum, LogLevelEnum)
from registry.exceptions.harvesting import InternalServerError
from registry.models.harvest import (HarvestingJob, HarvestingLog,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import DatasetMetadataRecord
from registry.models.service import CatalogueService
from registry.ows_lib.client.core import OgcClient
from registry.ows_lib.csw.csw import CatalogueServiceClient
from registry.tasks.harvest import (HarvestingTask, call_fetch_records,
                                    call_fetch_total_records,
                                    call_md_metadata_file_to_db)
from rest_framework import status
from tests.django.utils import MockResponse


def side_effect(request, timeout):
    if "GetRecords" in request.url:
        return MockResponse(
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/csw/get_records.xml')))
    elif "hits" in request.url:
        return MockResponse(
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/csw/hits.xml')))


# a GetRecords answer which is well typed and simply names no records at all - the answer which
# makes fetch_total_records fall back to the csw:Record type names
ZERO_RECORDS = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2">'
    '<csw:SearchResults numberOfRecordsMatched="0" numberOfRecordsReturned="0"'
    ' elementSet="summary" nextRecord="0" />'
    '</csw:GetRecordsResponse>'
)


def logging_response(request, content, status_code):
    """a MockResponse which knows the request it answers; the harvesting logs read the url of the
    response out of its request"""
    response = MockResponse(content=content, status_code=status_code)
    response.request = request
    return response


TOTAL_RECORDS = 30
MAX_RECORDS_PARAM = re.compile(r"maxRecords=(\d+)")
START_POSITION_PARAM = re.compile(r"startPosition=(\d+)")

REFUSED = ('<ExceptionReport><Exception exceptionCode="InvalidParameterValue"'
           ' exceptionText="maxRecords too large"/></ExceptionReport>')


def get_records_document(start_position, answered, total=TOTAL_RECORDS):
    """a well typed GetRecordsResponse carrying `answered` gmd:MD_Metadata records"""
    records = "".join(
        f'<gmd:MD_Metadata gco:id="r{start_position + i}"/>' for i in range(answered))
    return ('<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"'
            ' xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gco="http://www.isotc211.org/2005/gco">'
            f'<csw:SearchResults numberOfRecordsMatched="{total}"'
            f' numberOfRecordsReturned="{answered}" elementSet="full" nextRecord="0">'
            f'{records}</csw:SearchResults></csw:GetRecordsResponse>')


def csw_with_max_records_limit(limit, hits_always_ok=False):
    """a catalogue which refuses every GetRecords request asking for more than `limit` records -
    the usual answer to a too-large maxRecords - and which otherwise answers exactly what it is
    asked for, never more records than the catalogue holds (#694)"""
    def answer(request, timeout):
        max_records = MAX_RECORDS_PARAM.search(request.url)
        if max_records is None:
            # the count query of fetch_total_records asks for no page at all
            return logging_response(
                request, get_records_document(1, 0), status.HTTP_200_OK)
        wanted = int(max_records.group(1))
        is_hits = "resultType=hits" in request.url
        if wanted > limit and not (hits_always_ok and is_hits):
            return logging_response(request, REFUSED, status.HTTP_400_BAD_REQUEST)
        start = int(START_POSITION_PARAM.search(request.url).group(1))
        if is_hits:
            return logging_response(
                request, get_records_document(start, 0), status.HTTP_200_OK)
        answered = min(wanted, TOTAL_RECORDS - start + 1)
        return logging_response(
            request, get_records_document(start, answered), status.HTTP_200_OK)
    return answer


def csw_refusing_everything(request, timeout):
    """a catalogue which answers every GetRecords with the same refusal"""
    return logging_response(request, REFUSED, status.HTTP_400_BAD_REQUEST)


def side_effect_broken_fallback(fallback_status_code):
    """a catalogue whose default query answers no records and whose csw:Record fallback answers with
    the given status code"""
    def answer(request, timeout):
        if "csw%3ARecord" in request.url:
            return logging_response(
                request, "<html>the catalogue refuses the fallback</html>",
                fallback_status_code)
        return logging_response(request, ZERO_RECORDS, status.HTTP_200_OK)
    return answer


# the answer of a catalogue which refuses the constraint carrying GetRecords (#815): a plain http
# answer, a parseable document and an exception report whose prefix the substring test missed
OWS_EXCEPTION_REPORT = (
    '<ows:ExceptionReport xmlns:ows="http://www.opengis.net/ows" version="1.2.0">'
    '<ows:Exception exceptionCode="NoApplicableCode">'
    '<ows:ExceptionText>An unexpected error occured: Error in XML document</ows:ExceptionText>'
    '</ows:Exception></ows:ExceptionReport>')

# a response document which is well typed but simply carries no SearchResults node
NO_SEARCH_RESULTS = ('<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"'
                     ' numberOfRecordsReturned="0" nextRecord="0" />')


def side_effect_namespaced_exception_report(request, timeout):
    """a catalogue which answers every GetRecords with a namespaced exception report and a status
    which reads as an answer (#815)"""
    return logging_response(request, OWS_EXCEPTION_REPORT, status.HTTP_200_OK)


def side_effect_without_search_results(request, timeout):
    """a catalogue which answers every GetRecords with a response document which names no
    SearchResults node"""
    return logging_response(request, NO_SEARCH_RESULTS, status.HTTP_200_OK)


def setup_capabilitites_file():
    csw_2: CatalogueService = CatalogueService.objects.get(
        pk="3df586c6-b89b-4ce5-980a-12dc3ca23df2")
    csw_3: CatalogueService = CatalogueService.objects.get(
        pk="57cf66c2-3bde-49ad-b76e-bae49da57516")

    cap_file = open(
        f"{BASE_DIR}/tests/django/test_data/capabilities/csw/2.0.2.xml", mode="rb")

    csw_2.xml_backup_file = SimpleUploadedFile(
        'capabilitites.xml', cap_file.read())
    csw_2.save()

    cap_file = open(
        f"{BASE_DIR}/tests/django/test_data/capabilities/csw/2.0.2.xml", mode="rb")

    csw_3.xml_backup_file = SimpleUploadedFile(
        'capabilitites.xml', cap_file.read())
    csw_3.save()

    cap_file.close()


class HarvestingGetHitsTaskTest(TransactionTestCase):

    fixtures = ['test_users.json', 'test_keywords.json', 'test_csw.json']

    def setUp(self):
        setup_capabilitites_file()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch("celery.canvas.Signature.apply_async", return_value=None)
    @patch("celery.canvas.Signature.apply", return_value=None)
    @patch("celery.canvas.chord.apply_async", return_value=None)
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect
    )
    def test_success(self, mocked_send_request, mocked_chord_apply_async, mocked_apply, mocked_apply_async, mocked_on_commit):
        call_fetch_total_records.delay(harvesting_job_id=1)
        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        self.assertEqual(harvesting_job.total_records, 447773)

    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect_broken_fallback(status.HTTP_500_INTERNAL_SERVER_ERROR)
    )
    def test_failing_fallback_is_the_response_being_checked(self, mocked_send_request):
        """the csw:Record fallback is the response which gets checked and not the first response,
        which named no records on purpose: a server error of the fallback is the retryable error,
        where the unfixed check went on and failed on the missing SearchResults node (#689)"""
        with self.assertRaises(InternalServerError):
            call_fetch_total_records.run(harvesting_job_id=1)

        # both the default query and the fallback were answered
        self.assertEqual(mocked_send_request.call_count, 2)
        # and a harvesting worker retries exactly this error
        self.assertIn(InternalServerError, HarvestingTask.autoretry_for)

    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect_broken_fallback(status.HTTP_400_BAD_REQUEST)
    )
    def test_refused_fallback_is_logged_and_ends_without_records(self, mocked_send_request):
        """a 4xx is an answer and not an outage: it ends the run with zero records, and it is the
        fallback which is logged with its own url and status (#689)"""
        self.assertEqual(call_fetch_total_records.run(harvesting_job_id=1), 0)

        fallback_url = mocked_send_request.call_args_list[-1].kwargs["request"].url
        errors = HarvestingLog.objects.filter(
            harvesting_job_id=1, description="Response Error")
        self.assertTrue(errors.exists())
        logged = errors.first().extented_description.read().decode("UTF-8")
        self.assertIn(fallback_url, logged)
        self.assertIn("'status_code': 400", logged)
        self.assertEqual(errors.first().kind, LogKindEnum.REMOTE_ERROR.value)
        self.assertEqual(HarvestingJob.objects.get(pk=1).total_records, 0)

    def test_server_error_status_is_compared_as_a_range(self):
        """'>= 500 <= 600' is a chained comparison which simply means '>= 500'; a status outside the
        server error class is an answer to read, not a reason to retry (#689)"""
        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        request = SimpleNamespace(url="https://example.org/csw?REQUEST=GetRecords")

        for status_code in (400, 404, 700):
            with self.subTest(status_code=status_code):
                self.assertTrue(harvesting_job._check_xml_response(
                    logging_response(request, "<html>refused</html>", status_code)))

        with self.assertRaises(InternalServerError):
            harvesting_job._check_xml_response(
                logging_response(request, "<html>unavailable</html>", 503))

    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect_namespaced_exception_report
    )
    def test_namespaced_exception_report_is_the_response_being_logged(self, mocked_send_request):
        """an exception report refuses the request whichever prefix the service gives its element,
        and it is the Response Error of #689 which ends the run: the substring test only knew the
        unprefixed report, went on to read the count out of this one and aborted the whole harvest
        with the AttributeError of the missing SearchResults node (#815)"""
        self.assertEqual(call_fetch_total_records.run(harvesting_job_id=1), 0)

        # the refusal is an answer, so nothing is asked a second time
        self.assertEqual(mocked_send_request.call_count, 1)
        url = mocked_send_request.call_args_list[-1].kwargs["request"].url
        errors = HarvestingLog.objects.filter(
            harvesting_job_id=1, description="Response Error")
        self.assertTrue(errors.exists())
        logged = errors.first().extented_description.read().decode("UTF-8")
        self.assertIn(url, logged)
        self.assertIn("ows:ExceptionReport", logged)
        self.assertEqual(errors.first().kind, LogKindEnum.REMOTE_ERROR.value)
        self.assertEqual(HarvestingJob.objects.get(pk=1).total_records, 0)

    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect_without_search_results
    )
    def test_answer_without_search_results_ends_the_run_without_records(self, mocked_send_request):
        """a document which names no SearchResults names no records: the run goes on to the fallback
        of #689 and ends with the log of a count which stays 0 instead of raising on the missing
        node (#815)"""
        self.assertEqual(call_fetch_total_records.run(harvesting_job_id=1), 0)

        # the count is missing in the default query's answer, so the csw:Record fallback is asked
        self.assertEqual(mocked_send_request.call_count, 2)
        self.assertTrue(HarvestingLog.objects.filter(
            harvesting_job_id=1, description="GetTotalRecords failed",
            level=LogLevelEnum.ERROR.value).exists())
        self.assertEqual(HarvestingJob.objects.get(pk=1).total_records, 0)

    def test_exception_report_is_found_whatever_its_prefix(self):
        """the report of a refusing service is namespace qualified and the prefix is its own choice,
        so the local name is what identifies it - and the requested document is no report (#815)"""
        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        request = SimpleNamespace(url="https://example.org/csw?REQUEST=GetRecords")

        for report in (
                OWS_EXCEPTION_REPORT,
                '<ExceptionReport xmlns="http://www.opengis.net/ows" version="1.2.0"/>',
                REFUSED,
                '<ServiceExceptionReport><ServiceException code="NoSuchParameter">'
                'unknown parameter</ServiceException></ServiceExceptionReport>'):
            with self.subTest(report=report):
                self.assertTrue(harvesting_job._check_xml_response(
                    logging_response(request, report, status.HTTP_200_OK)))

        self.assertFalse(harvesting_job._check_xml_response(
            logging_response(request, get_records_document(1, 1), status.HTTP_200_OK)))

    def test_missing_search_results_node_names_no_records(self):
        """the count of a document without SearchResults is no records and not an AttributeError,
        which is what no answer of the remote service should turn into (#815)"""
        response = logging_response(
            SimpleNamespace(url="https://example.org/csw?REQUEST=GetRecords"),
            NO_SEARCH_RESULTS, status.HTTP_200_OK)
        self.assertEqual(HarvestingJob().get_total_records(response), 0)


class HarvestingGetRecordsTaskTest(TransactionTestCase):

    fixtures = ['test_users.json', 'test_keywords.json', 'test_csw.json']

    def setUp(self):
        setup_capabilitites_file()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect
    )
    def test_success(self, mocked_run_checks):

        call_fetch_records.delay(harvesting_job_id=1, start_position=1)
        temporary_md_files_count: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.filter(
            job__id=1).count()
        self.assertEqual(temporary_md_files_count, 10)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_recovered_page_is_not_duplicated(self, send_request):
        call_fetch_records.delay(harvesting_job_id=1, start_position=1)
        before = list(TemporaryMdMetadataFile.objects.filter(job_id=1).values_list('pk', flat=True))
        call_fetch_records.delay(harvesting_job_id=1, start_position=1, recovering=True)
        self.assertCountEqual(
            TemporaryMdMetadataFile.objects.filter(job_id=1).values_list('pk', flat=True), before)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_recovered_page_is_not_requested_again(self, send_request):
        """a page which is stored is complete, so a redelivery of it asks nothing of the remote
        service - the deduplication must be visible in the requests sent and not only in the rows
        left behind (#688)"""
        call_fetch_records.delay(harvesting_job_id=1, start_position=1)
        self.assertEqual(send_request.call_count, 1)

        call_fetch_records.delay(harvesting_job_id=1, start_position=1, recovering=True)
        call_fetch_records.delay(harvesting_job_id=1, start_position=1, recovering=True)

        self.assertEqual(send_request.call_count, 1)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_page_which_is_missing_is_requested_when_recovering(self, send_request):
        """the recovery of a worker restart still downloads the pages which never arrived"""
        call_fetch_records.delay(harvesting_job_id=1, start_position=1)
        call_fetch_records.delay(harvesting_job_id=1, start_position=11, recovering=True)

        self.assertEqual(send_request.call_count, 2)
        self.assertEqual(TemporaryMdMetadataFile.objects.filter(job_id=1).count(), 20)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(OgcClient, "send_request")
    def test_a_refused_page_leaves_a_trace_of_the_records_it_did_not_deliver(self, send_request):
        """a page which the catalogue refuses is not nothing: the records it should have carried
        are missing from this snapshot, and only a run which says so can be answered as an
        incomplete one (#690)"""
        def refused(request, timeout):
            response = MockResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content='<ExceptionReport><Exception exceptionCode="TooLargeBestRecords"'
                        ' exceptionText="maxRecords too large"/></ExceptionReport>')
            response.request = request
            return response
        send_request.side_effect = refused

        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        harvesting_job.total_records = 100
        harvesting_job.save()

        call_fetch_records.delay(harvesting_job_id=1, start_position=1)

        self.assertEqual(TemporaryMdMetadataFile.objects.filter(job_id=1).count(), 0)
        short_pages = HarvestingLog.objects.filter(
            harvesting_job_id=1, kind=LogKindEnum.COUNT_MISSMATCH.value)
        self.assertEqual(short_pages.count(), 1)
        self.assertEqual(short_pages.first().description, "0<50")
        logged = short_pages.first().extented_description.read().decode("UTF-8")
        self.assertIn("Only 0 received from 50 possible records.", logged)
        self.assertIn("startPosition=1", logged)


class TemporaryMdMetadataFileToDbTaskTest(TransactionTestCase):

    fixtures = ['test_users.json', 'test_keywords.json', 'test_csw.json']

    def setUp(self):
        setup_capabilitites_file()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    def test_success(self, ):

        md_file = open(
            f"{BASE_DIR}/tests/django/test_data/csw/md_metadata.xml", mode="rb")

        temporary_md_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.get(
            pk="1")

        temporary_md_file.md_metadata_file = SimpleUploadedFile(
            'capabilitites.xml', md_file.read())
        temporary_md_file.save()
        md_file.close()

        harvesting_job: HarvestingJob = temporary_md_file.job

        call_md_metadata_file_to_db.delay(
            md_metadata_file_id="1")

        # temporary object was deleted
        self.assertEqual(
            TemporaryMdMetadataFile.objects.filter(job__id=2).count(), 0)
        # job is done
        self.assertFalse(harvesting_job.done_at, None)
        # dataset metadata object was created
        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)


class HarvestingStepSizeTest(TransactionTestCase):
    """the page size a run works with is what the catalogue answers (#694)"""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_csw.json']

    def setUp(self):
        setup_capabilitites_file()

    @staticmethod
    def requested_sizes(send_request):
        """the maxRecords values of all requests which asked for a page"""
        return [MAX_RECORDS_PARAM.search(call.kwargs["request"].url).group(1)
                for call in send_request.call_args_list
                if MAX_RECORDS_PARAM.search(call.kwargs["request"].url)]

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch("celery.canvas.Signature.apply_async", return_value=None)
    @patch("celery.canvas.Signature.apply", return_value=None)
    @patch("celery.canvas.chord.apply_async", return_value=None)
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=csw_with_max_records_limit(10)
    )
    def test_step_size_is_probed_before_the_fan_out_is_planned(self, mocked_send_request, *mocked_canvas):
        """a catalogue which refuses maxRecords above 10 is asked 50, 25 and 12 and answers 6 -
        and the fan-out is planned with 6, so the refused size never reaches the real pages"""
        call_fetch_total_records.run(harvesting_job_id=1)

        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        self.assertEqual(harvesting_job.total_records, TOTAL_RECORDS)
        self.assertEqual(harvesting_job.max_step_size, 6)
        self.assertEqual(self.requested_sizes(mocked_send_request),
                         ["50", "25", "12", "6"])

        descriptions = list(HarvestingLog.objects.filter(
            harvesting_job_id=1).values_list("description", flat=True))
        self.assertIn(
            "catalogue refused GetRecords with maxRecords=50, probing 25", descriptions)
        self.assertIn(
            "catalogue refused GetRecords with maxRecords=25, probing 12", descriptions)
        self.assertIn(
            "catalogue refused GetRecords with maxRecords=12, probing 6", descriptions)
        self.assertIn(
            "catalogue answers GetRecords with maxRecords=6;"
            " the harvest is planned with that size", descriptions)
        self.assertTrue(
            any("step size 6" in description for description in descriptions),
            "the fan-out log names the size the run plans with")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch("celery.canvas.Signature.apply_async", return_value=None)
    @patch("celery.canvas.Signature.apply", return_value=None)
    @patch("celery.canvas.chord.apply_async", return_value=None)
    @patch.object(CatalogueServiceClient, "advertised_max_records", return_value=25)
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=csw_with_max_records_limit(25)
    )
    def test_capabilities_limit_starts_the_probe(self, mocked_send_request, mocked_hint, *mocked_canvas):
        """a limit named by the capabilities is where the probing starts - but the service is
        still the one which answers, the hint is only the first thing asked of it (#694)"""
        call_fetch_total_records.run(harvesting_job_id=1)

        self.assertEqual(self.requested_sizes(mocked_send_request), ["25"])
        self.assertEqual(HarvestingJob.objects.get(pk=1).max_step_size, 25)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch("celery.canvas.Signature.apply_async", return_value=None)
    @patch("celery.canvas.Signature.apply", return_value=None)
    @patch("celery.canvas.chord.apply_async", return_value=None)
    @patch.object(CatalogueServiceClient, "advertised_max_records", return_value=1000)
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=csw_with_max_records_limit(1000)
    )
    def test_capabilities_limit_never_raises_the_planned_size(self, mocked_send_request, mocked_hint, *mocked_canvas):
        """a limit above the size the run starts from is no reason to ask bigger: the probe
        starts at the planned size"""
        call_fetch_total_records.run(harvesting_job_id=1)

        self.assertEqual(self.requested_sizes(mocked_send_request), ["50"])
        self.assertEqual(HarvestingJob.objects.get(pk=1).max_step_size, 50)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch("celery.canvas.Signature.apply_async", return_value=None)
    @patch("celery.canvas.Signature.apply", return_value=None)
    @patch("celery.canvas.chord.apply_async", return_value=None)
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=csw_with_max_records_limit(10)
    )
    def test_catalogue_with_limit_below_the_step_size_is_harvested_completely(
            self, mocked_send_request, *mocked_canvas):
        """the operator of a catalogue whose limit is 10 knows nothing of it: the run probes,
        plans and fetches all its pages at 6 records and nothing stays missing (#694)"""
        call_fetch_total_records.run(harvesting_job_id=1)

        for start_position in (1, 7, 13, 19, 25):
            call_fetch_records.run(
                harvesting_job_id=1, start_position=start_position)

        self.assertEqual(
            TemporaryMdMetadataFile.objects.filter(job_id=1).count(), TOTAL_RECORDS)
        self.assertFalse(HarvestingLog.objects.filter(
            harvesting_job_id=1,
            kind=LogKindEnum.COUNT_MISSMATCH.value).exists(),
            "a run which fetched every page answers no trace of missing records")

        annotated: HarvestingJob = HarvestingJob.objects.with_process_info().get(pk=1)
        self.assertGreaterEqual(annotated.progress, 0)
        self.assertLessEqual(annotated.progress, 100)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=csw_with_max_records_limit(10, hits_always_ok=True)
    )
    def test_range_of_a_refused_page_is_fetched_at_halved_sizes(self, mocked_send_request):
        """a catalogue which answers the size question but refuses the real pages above 10
        records still sees its page complete: the missing part of the range is asked with 25,
        12 and then 6 records, and its rest is harvested at the size which answered (#694)"""
        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        harvesting_job.total_records = TOTAL_RECORDS
        harvesting_job.save()

        call_fetch_records.run(harvesting_job_id=1, start_position=1)

        self.assertEqual(
            TemporaryMdMetadataFile.objects.filter(job_id=1).count(), TOTAL_RECORDS)
        self.assertEqual(
            self.requested_sizes(mocked_send_request),
            ["50", "25", "12", "6", "6", "6", "6", "6", "6"])

        # the timeout scaled with the sizes asked for: 50, 25 and 12 records had 70, 40 and 24 s
        self.assertEqual(
            [call.kwargs["timeout"] for call in mocked_send_request.call_args_list][:3],
            [70, 40, 24])

        descriptions = list(HarvestingLog.objects.filter(
            harvesting_job_id=1,
            level=LogLevelEnum.WARNING.value).values_list("description", flat=True))
        self.assertIn(
            "GetRecords with maxRecords=50 at startPosition 1 was refused,"
            " the missing part is asked with 25", descriptions)
        self.assertIn(
            "GetRecords with maxRecords=25 at startPosition 1 was refused,"
            " the missing part is asked with 12", descriptions)
        self.assertIn(
            "GetRecords with maxRecords=12 at startPosition 1 was refused,"
            " the missing part is asked with 6", descriptions)
        self.assertFalse(HarvestingLog.objects.filter(
            harvesting_job_id=1,
            kind=LogKindEnum.COUNT_MISSMATCH.value).exists())

        annotated: HarvestingJob = HarvestingJob.objects.with_process_info().get(pk=1)
        self.assertGreaterEqual(annotated.progress, 0)
        self.assertLessEqual(annotated.progress, 100)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=csw_refusing_everything
    )
    def test_a_range_refused_at_every_size_stops_at_the_floor_and_leaves_the_trace(
            self, mocked_send_request):
        """the halving is bounded: from the step size of 50 it asks 50, 25, 12, 6, 3 and 1,
        and what stays missing is answered the way #690 defines it"""
        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        harvesting_job.total_records = 100
        harvesting_job.save()

        call_fetch_records.run(harvesting_job_id=1, start_position=1)

        self.assertEqual(self.requested_sizes(mocked_send_request),
                         ["50", "25", "12", "6", "3", "1"])
        self.assertEqual(mocked_send_request.call_count, 6)
        self.assertEqual(
            TemporaryMdMetadataFile.objects.filter(job_id=1).count(), 0)
        traces = HarvestingLog.objects.filter(
            harvesting_job_id=1, kind=LogKindEnum.COUNT_MISSMATCH.value)
        self.assertEqual(traces.count(), 1)
        self.assertEqual(traces.first().description, "0<50")

    def test_request_timeout_scales_with_the_page_size(self):
        """a page which is only slow must not read as a page which does not work (#694)"""
        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        self.assertEqual(harvesting_job.get_request_timeout(50), 70)
        self.assertEqual(harvesting_job.get_request_timeout(500), 610)
        self.assertEqual(harvesting_job.get_request_timeout(32767), 900)
