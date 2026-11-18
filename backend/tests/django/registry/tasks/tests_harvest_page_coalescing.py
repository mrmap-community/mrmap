"""Concurrent deliveries of one GetRecords page ask the catalogue once (#1411).

A scheduled fan-out which fires again while its previous run still works hands the
same page to two workers. The saved-page check of #688 covers a redelivery, a
retry and a recovery - and only a page whose records are already in the backlog,
which a page *still downloading* is not. A plain second delivery does not ask that
check at all (``check_existing`` in ``call_fetch_records``), so before this change
two overlapping deliveries downloaded one page twice, and the row count under the
lock of the job settled them only after both requests were over.

What closes the window is a claim: the delivery which holds a page's claim asks the
catalogue, and a delivery which arrives *while that claim is held* joins the
outcome instead of asking. Joining is what overlaps - the outcome of a finished
flight answers nobody later, so an attempt which comes after it asks the page
again, exactly as it did before this change and for the same reason the answers of
#690 and #694 exist: a refusing catalogue is asked again, and records an attempt
did not store stay visible as missing.

The overlapping delivery is played by a claim planted in the cache rather than by a
second worker, because the two differ in nothing the model can tell: what a
delivery sees is a claim held by someone else, an outcome below it, or neither. The
one test which wants a holder that answers *while* the other waits runs it in a
thread, since that path only touches the cache and never the database.
"""

from threading import Thread
from time import sleep
from unittest.mock import patch

from django.core.cache import cache
from django.test import TransactionTestCase
from django.test.utils import override_settings
from django.utils import timezone
from extras.locks import SingleFlight
from registry.enums.harvesting import LogKindEnum, LogLevelEnum
from registry.exceptions.harvesting import InternalServerError
from registry.models.harvest import (PAGE_EMPTY, PAGE_REFUSED, PAGE_STORED,
                                     HarvestingJob, HarvestingLog,
                                     TemporaryMdMetadataFile)
from registry.ows_lib.client.core import OgcClient
from registry.tasks.harvest import call_fetch_records
from rest_framework import status
from tests.django.registry.tasks.tests_harvesting import (
    MAX_RECORDS_PARAM, REFUSED, START_POSITION_PARAM, csw_refusing_everything,
    get_records_document, logging_response, setup_capabilitites_file)

LOC_MEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "harvest-page-coalescing-tests",
    },
}

#: records the catalogue holds, enough for more than one page of the step size a
#: run plans with
CATALOGUE_RECORDS = 200

#: the size a run without a probe asks with - the max_step_size of the model
PAGE_SIZE = 50

#: the page of the catalogue: its first PAGE_SIZE records
FIRST_PAGE = (1, PAGE_SIZE)

#: every size a page of 50 records is halved down to before the floor of #694
HALVED_SIZES = [(1, 50), (1, 25), (1, 12), (1, 6), (1, 3), (1, 1)]

#: what a delivery which joined the refused first step asks of its own
HALVED_SIZES_AFTER_A_JOIN = HALVED_SIZES[1:]

#: a page is refused/answered by another delivery: no celery task of the new run
NO_TASK_PUBLISH = patch("celery.canvas.Signature.apply_async", return_value=None)


def catalogue(total_records, limit=None):
    """a catalogue which answers exactly what it is asked for, never more records
    than it holds; `limit` is the size it refuses with an exception report"""
    def answer(request, timeout):
        max_records = MAX_RECORDS_PARAM.search(request.url)
        start = START_POSITION_PARAM.search(request.url)
        if max_records is None or start is None:
            return logging_response(
                request, get_records_document(1, 0, total=total_records),
                status.HTTP_200_OK)
        wanted = int(max_records.group(1))
        position = int(start.group(1))
        if limit is not None and wanted > limit:
            return logging_response(request, REFUSED, status.HTTP_400_BAD_REQUEST)
        answered = min(wanted, max(0, total_records - position + 1))
        return logging_response(
            request,
            get_records_document(position, answered, total=total_records),
            status.HTTP_200_OK)
    return answer


def answers_without_records(request, timeout):
    """a catalogue whose answer is well typed and simply carries no record at all -
    the answer which costs a request, stores nothing and is not a refusal"""
    return logging_response(
        request, get_records_document(1, 0, total=0), status.HTTP_200_OK)


def answers_with_a_server_error(request, timeout):
    """a catalogue which cannot answer at all; the class of answer which raises for
    a retry instead of being stored or refused (#689)"""
    return logging_response(
        request, "<html>the catalogue is gone</html>",
        status.HTTP_502_BAD_GATEWAY)


def page_request(job, start_position, max_records=None):
    """The GetRecords request a delivery of this page asks with.

    The same request ``HarvestingJob.fetch_records`` builds, because the claim of
    a page is named after exactly that request - the fingerprint of a differently
    built one would be a different page.
    """
    client = job.service.client
    return client.get_records_request(
        max_records=max_records or job.max_step_size,
        start_position=start_position,
        result_type="results",
        xml_constraint=client.get_constraint(record_types=job.get_record_types()))


def claim_held_by_another_worker(job, request, lease_seconds=60):
    """Claim the page of `request` as some other worker would, and return its claim.

    Returns:
        SingleFlight: the claim, so a test can leave an outcome below its key or
            watch it lapse
    """
    claim = SingleFlight(
        key=job._page_claim_key(request), lease_seconds=lease_seconds)
    assert claim.acquire()
    return claim


def claim_held_with_answer(job, request, outcome, lease_seconds=60):
    """Hold the claim of a page and leave `outcome` below it.

    This is the moment a holder is in after its request answered and before it
    hands the lease back: the claim is held, so the delivery under test is a
    waiter, and a waiter is the only delivery an outcome may answer.
    """
    claim = claim_held_by_another_worker(job, request, lease_seconds)
    cache.set(claim.answer_key, outcome, lease_seconds)
    return claim


@override_settings(CACHES=LOC_MEM)
class HarvestPageCoalescingTest(TransactionTestCase):
    """one page, two overlapping deliveries, one request"""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_csw.json']

    def setUp(self):
        setup_capabilitites_file()
        # the claim of a page lives in the cache, which no test run rolls back
        # with the database
        cache.clear()
        self.job = HarvestingJob.objects.get(pk=1)
        self.job.total_records = CATALOGUE_RECORDS
        self.job.save()

    @staticmethod
    def requested_pages(send_request):
        """the (startPosition, maxRecords) of every request which asked for a page"""
        pages = []
        for call in send_request.call_args_list:
            url = call.kwargs["request"].url
            size = MAX_RECORDS_PARAM.search(url)
            position = START_POSITION_PARAM.search(url)
            if size and position:
                pages.append((int(position.group(1)), int(size.group(1))))
        return pages

    def stored_pages(self, job_id):
        """the records of one run which are in the backlog"""
        return TemporaryMdMetadataFile.objects.filter(job_id=job_id).count()

    def traces(self, job_id=1):
        """the traces of records a page did not deliver (#690)"""
        return HarvestingLog.objects.filter(
            harvesting_job_id=job_id, kind=LogKindEnum.COUNT_MISSMATCH.value)

    def warnings(self, job_id=1):
        """what the run said about the sizes it had to give up on"""
        return list(HarvestingLog.objects.filter(
            harvesting_job_id=job_id,
            level=LogLevelEnum.WARNING.value).values_list("description", flat=True))

    @staticmethod
    def close(job):
        """the run is over, so another one may start for the same catalogue

        ``only_one_unfinished_job_per_service`` is a partial unique index: a second
        run of one catalogue is only possible once the first one is done. The row is
        written directly, because closing a run is not what these tests are about.
        """
        HarvestingJob.objects.filter(pk=job.pk).update(done_at=timezone.now())

    # -- what overlaps: the coalescing itself ---------------------------------

    @override_settings(HARVESTING_PAGE_WAIT_CAP_SECONDS=3)
    @patch.object(OgcClient, "send_request")
    def test_a_delivery_joins_the_page_a_running_delivery_fetches(self, send_request):
        """a delivery which arrives while the page is being fetched waits for the
        answer of the one who fetches it, instead of making a parallel request"""
        send_request.side_effect = catalogue(CATALOGUE_RECORDS)
        claim = claim_held_by_another_worker(
            self.job, page_request(self.job, 1), lease_seconds=5)

        # the holder finishes its request while this delivery waits for it
        holder = Thread(target=self.answer_after,
                        args=(claim, (PAGE_STORED, PAGE_SIZE)), daemon=True)
        holder.start()
        self.addCleanup(holder.join)

        received = call_fetch_records.run(harvesting_job_id=1, start_position=1)

        self.assertEqual(self.requested_pages(send_request), [])
        self.assertEqual(received, PAGE_SIZE)
        self.assertEqual(self.stored_pages(1), 0,
                         "the page is stored by the delivery which fetched it")

    @staticmethod
    def answer_after(claim, outcome):
        """the holder of a page comes back from its request a moment later"""
        sleep(0.05)
        claim.finish(outcome)

    @patch.object(OgcClient, "send_request")
    def test_a_page_answered_under_a_held_claim_is_not_asked_again(self, send_request):
        """the holder already stored the page and has not handed its lease back
        yet: the delivery which arrives in that moment takes the count the holder
        stored and sends no request of its own - the duplicate download this issue
        is about. #688's saved-page check would answer this page too, but it only
        runs for a recovery, a retry or a redelivery; for a plain delivery the
        claim is all that stands between the catalogue and a second download."""
        send_request.side_effect = catalogue(CATALOGUE_RECORDS)
        claim_held_with_answer(
            self.job, page_request(self.job, 1), (PAGE_STORED, PAGE_SIZE))

        received = call_fetch_records.run(harvesting_job_id=1, start_position=1)

        self.assertEqual(self.requested_pages(send_request), [])
        self.assertEqual(received, PAGE_SIZE)
        self.assertFalse(self.traces().exists(),
                         "a page which arrived leaves no trace of missing records")

    # -- what does not overlap: nothing is silenced ---------------------------

    @patch.object(OgcClient, "send_request")
    def test_a_delivery_after_the_flight_ended_asks_the_page_again(
            self, send_request):
        """the outcome of a finished flight answers nobody later.

        An attempt which comes after a page was fetched is a new attempt: it asks,
        like it did before this change. The leftover of the finished flight is not
        an answer for it - a refused page has to be asked again (#694) and records
        an earlier attempt did not store stay missing until somebody asks for them
        (#690). Two deliveries of one page which do not overlap therefore cost two
        requests, and the storage of the page settles the duplicate (#688).
        """
        send_request.side_effect = catalogue(CATALOGUE_RECORDS)

        first = call_fetch_records.run(harvesting_job_id=1, start_position=1)
        second = call_fetch_records.run(harvesting_job_id=1, start_position=1)

        self.assertEqual(self.requested_pages(send_request),
                         [FIRST_PAGE, FIRST_PAGE])
        self.assertEqual((first, second), (PAGE_SIZE, PAGE_SIZE))
        self.assertEqual(self.stored_pages(1), PAGE_SIZE,
                         "the second copy of the page stores nothing")
        urls = TemporaryMdMetadataFile.objects.filter(
            job_id=1).values_list("requested_url", flat=True)
        self.assertEqual(len(set(urls)), 1, "one page, one request url")

    @patch.object(OgcClient, "send_request", side_effect=csw_refusing_everything)
    def test_a_redelivered_refused_page_asks_every_size_again(self, send_request):
        """a refusal is not an answer for the next attempt: the redelivery halves
        the whole page again down to the floor of #694, and both attempts say what
        stayed missing (#690) - the accounting a run is judged incomplete by"""
        self.job.total_records = 100
        self.job.save()

        first = call_fetch_records.run(harvesting_job_id=1, start_position=1)
        second = call_fetch_records.run(harvesting_job_id=1, start_position=1)

        self.assertEqual(self.requested_pages(send_request),
                         HALVED_SIZES * 2)
        self.assertEqual((first, second), (0, 0))
        self.assertEqual(self.stored_pages(1), 0)
        traces = self.traces()
        self.assertEqual(traces.count(), 2,
                         "both attempts say what this page did not deliver")
        self.assertEqual({trace.description for trace in traces}, {"0<50"})

    # -- a joined answer decides the same as an own one -----------------------

    @patch.object(OgcClient, "send_request", side_effect=csw_refusing_everything)
    def test_a_refusal_another_delivery_holds_is_joined_and_still_halves(
            self, send_request):
        """the halving of #694 decides from a joined refusal exactly as from an own
        one: the refused size is not asked a second time, and the rest of the range
        is asked at the halved sizes under claims of this delivery's own"""
        self.job.total_records = 100
        self.job.save()
        claim_held_with_answer(
            self.job, page_request(self.job, 1), (PAGE_REFUSED, 0))

        received = call_fetch_records.run(harvesting_job_id=1, start_position=1)

        self.assertEqual(self.requested_pages(send_request),
                         HALVED_SIZES_AFTER_A_JOIN)
        self.assertEqual(received, 0)
        self.assertIn(
            "GetRecords with maxRecords=50 at startPosition 1 was refused, the "
            "missing part is asked with 25", self.warnings())
        self.assertEqual(self.traces().count(), 1,
                         "the joiner accounts for the page it did not deliver")

    @patch.object(OgcClient, "send_request")
    def test_a_page_without_records_is_joined_and_still_halves(self, send_request):
        """an answer which carries no record is not a refusal, and a delivery which
        joins one halves for the rest of the range and leaves the trace of #690"""
        send_request.side_effect = answers_without_records
        self.job.total_records = 100
        self.job.save()
        claim_held_with_answer(
            self.job, page_request(self.job, 1), (PAGE_EMPTY, 0))

        received = call_fetch_records.run(harvesting_job_id=1, start_position=1)

        self.assertEqual(self.requested_pages(send_request),
                         HALVED_SIZES_AFTER_A_JOIN)
        self.assertEqual(received, 0)
        self.assertEqual(self.stored_pages(1), 0)
        self.assertIn(
            "GetRecords with maxRecords=25 at startPosition 1 came back without"
            " records, the missing part is asked with 12", self.warnings())
        self.assertEqual(self.traces().count(), 1)

    # -- what must never collide ----------------------------------------------

    @patch.object(OgcClient, "send_request")
    def test_distinct_pages_of_one_run_never_share_a_claim(self, send_request):
        """the page after this one is a different question and is asked the moment
        it is delivered"""
        send_request.side_effect = catalogue(CATALOGUE_RECORDS)

        call_fetch_records.run(harvesting_job_id=1, start_position=1)
        call_fetch_records.run(harvesting_job_id=1, start_position=51)

        self.assertEqual(self.requested_pages(send_request),
                         [(1, PAGE_SIZE), (51, PAGE_SIZE)])
        self.assertEqual(self.stored_pages(1), 2 * PAGE_SIZE)
        self.assertFalse(self.traces().exists())

    @NO_TASK_PUBLISH
    @patch.object(OgcClient, "send_request")
    def test_two_runs_of_one_catalogue_never_share_a_page(self, send_request,
                                                          *patched_canvas):
        """two runs of one catalogue are two snapshots: the same page of the same
        service at the same position is asked for both of them, and what one run
        downloaded never lands in the backlog of the other"""
        send_request.side_effect = catalogue(CATALOGUE_RECORDS)
        call_fetch_records.run(harvesting_job_id=1, start_position=1)
        self.close(self.job)
        other = HarvestingJob.objects.create(
            service=self.job.service, total_records=CATALOGUE_RECORDS)

        call_fetch_records.run(harvesting_job_id=other.pk, start_position=1)

        self.assertEqual(self.requested_pages(send_request),
                         [FIRST_PAGE, FIRST_PAGE])
        self.assertEqual(self.stored_pages(1), PAGE_SIZE)
        self.assertEqual(self.stored_pages(other.pk), PAGE_SIZE)

    @NO_TASK_PUBLISH
    @patch.object(OgcClient, "send_request")
    def test_a_changed_constraint_is_a_different_page(self, send_request,
                                                      *patched_canvas):
        """the effective query is part of the fingerprint: a run which harvests
        other record types asks a different question at the same position, so it is
        never answered from the page of a run which harvests all of them"""
        send_request.side_effect = catalogue(CATALOGUE_RECORDS)
        call_fetch_records.run(harvesting_job_id=1, start_position=1)
        self.close(self.job)
        other = HarvestingJob.objects.create(
            service=self.job.service, total_records=CATALOGUE_RECORDS,
            harvest_services=False)

        call_fetch_records.run(harvesting_job_id=other.pk, start_position=1)

        self.assertEqual(len(self.requested_pages(send_request)), 2)
        urls = {call.kwargs["request"].url for call in send_request.call_args_list}
        self.assertEqual(len(urls), 2, "the two requests really do differ")

    # -- the claim: crash, expiry and giving up -------------------------------

    @override_settings(HARVESTING_PAGE_POLL_SECONDS=0.005,
                       HARVESTING_PAGE_POLL_MAX_SECONDS=0.02)
    @patch.object(OgcClient, "send_request")
    def test_a_claim_whose_holder_died_is_taken_over(self, send_request):
        """a claim expires with the request it protects, so a worker which died
        with a page hands it back to the next delivery instead of losing it"""
        send_request.side_effect = catalogue(CATALOGUE_RECORDS)
        # a claim nobody works under anymore, about to run out
        cache.add(self.job._page_claim_key(page_request(self.job, 1)),
                  "a-worker-which-died", 0.01)

        received = call_fetch_records.run(harvesting_job_id=1, start_position=1)

        self.assertEqual(self.requested_pages(send_request), [FIRST_PAGE])
        self.assertEqual(received, PAGE_SIZE)
        self.assertEqual(self.stored_pages(1), PAGE_SIZE)

    @override_settings(HARVESTING_PAGE_WAIT_CAP_SECONDS=0)
    @patch.object(OgcClient, "send_request")
    def test_a_holder_silent_past_the_wait_is_not_waited_for(self, send_request):
        """a delivery does not park a worker forever for a page it could fetch
        itself: past its wait it asks for the page, says so in the log and stores
        the page - the store of #688 settles the two deliveries afterwards"""
        send_request.side_effect = catalogue(CATALOGUE_RECORDS)
        claim_held_by_another_worker(self.job, page_request(self.job, 1))

        received = call_fetch_records.run(harvesting_job_id=1, start_position=1)

        self.assertEqual(self.requested_pages(send_request), [FIRST_PAGE])
        self.assertEqual(received, PAGE_SIZE)
        self.assertEqual(self.stored_pages(1), PAGE_SIZE)
        self.assertTrue(HarvestingLog.objects.filter(
            harvesting_job_id=1,
            level=LogLevelEnum.WARNING.value,
            description="fetched a page another delivery still claims",
        ).exists(), "the doubled request is not left unexplained")

    @patch.object(OgcClient, "send_request")
    def test_a_page_whose_request_failed_leaves_no_claim_behind(self, send_request):
        """the retry of a page which could not be asked at all must not wait out
        the claim of the attempt which failed (#689)"""
        send_request.side_effect = answers_with_a_server_error
        with self.assertRaises(InternalServerError):
            call_fetch_records.run(harvesting_job_id=1, start_position=1)

        send_request.side_effect = catalogue(CATALOGUE_RECORDS)
        received = call_fetch_records.run(
            harvesting_job_id=1, start_position=1, recovering=True)

        self.assertEqual(self.requested_pages(send_request),
                         [FIRST_PAGE, FIRST_PAGE])
        self.assertEqual(received, PAGE_SIZE)
        self.assertEqual(self.stored_pages(1), PAGE_SIZE)

    # -- the saved-page recovery of #688 stays as it was ----------------------

    @patch.object(OgcClient, "send_request")
    def test_a_redelivered_page_still_costs_no_request(self, send_request):
        """the saved-page recovery of #688 is not replaced by the claim: a page
        whose records are in the backlog is not asked again, recovery or not"""
        send_request.side_effect = catalogue(CATALOGUE_RECORDS)

        call_fetch_records.run(harvesting_job_id=1, start_position=1)
        call_fetch_records.run(
            harvesting_job_id=1, start_position=1, recovering=True)
        call_fetch_records.run(
            harvesting_job_id=1, start_position=1, recovering=True)

        self.assertEqual(self.requested_pages(send_request), [FIRST_PAGE])
        self.assertEqual(self.stored_pages(1), PAGE_SIZE)
