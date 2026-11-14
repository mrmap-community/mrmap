"""The retry mutation of a retained registration reference (#1265).

The api answers the failed work rows of a registration (#1263); this module
owns the one write #1265 adds on top: the authorized PATCH which asks the
collection to fetch THIS reference again. The counter arithmetic of the
decided retry lives with the task (``tests_collect_reference``); what is
pinned here is the door in front of it:

* only a decided FAILED reference of a registration is retryable, and only
  under a run which is running, or COMPLETED-with-import-errors (D3) - a
  FAILED or ABORTED run is never reopened through a reference;
* the ask is decided like the abort of a process: by the permission of the
  resource the process reports on - view is not enough, anonymous is out;
* the accepted ask dispatches the row's own ``collect_reference`` with its
  ``allow_failed`` authorization, addressed by the row pk and its owning
  process - never a harvesting task, never a new process;
* the row stays FAILED until the new attempt claims it: the mutation asks,
  it does not decide, and the verdict fields stay inspectable meanwhile;
* every other write of the endpoint (POST/PUT/DELETE) stays with the model
  permission it had before: the work row is the permit store of the queue.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TransactionTestCase
from django.utils import timezone
from guardian.shortcuts import assign_perm
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.enums.metadata import ReferenceErrorKind, ReferenceWorkStateEnum
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.models.metadata import MetadataContact
from registry.models.service import WebMapService
from registry.tasks import service as service_tasks
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
# the request format name of the json:API renderer, not its media type
FORMAT = "vnd.api+json"
OLD = timezone.now() - timedelta(hours=2)


class ReferenceRetryApiTests(TransactionTestCase):
    """The PATCH door of the reference work queue, end to end."""

    def setUp(self):
        super().setUp()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        contact = MetadataContact.objects.create(name='retry api contact')
        self.service = WebMapService.objects.create(
            title='Retry api service', version=130, origin=1,
            service_url='http://retry.example.org/wms',
            metadata_contact=contact, service_contact=contact)
        self.user = get_user_model().objects.create_user(
            username='retry-editor', password='retry-editor')
        self.anonymous = APIClient()
        self.editor = APIClient()
        self.editor.force_authenticate(user=self.user)

    def _process(self, status=ProcessStatusEnum.COMPLETED, **overrides):
        values = dict(
            process_type='registering', phase='collect_metadata_records',
            description='', status=status,
            references_plan_sealed=True, references_total=1,
            references_stored=0, references_failed=1, references_skipped=0,
            related_resource_type=ContentType.objects.get_for_model(
                WebMapService),
            related_id=self.service.pk)
        if status == ProcessStatusEnum.COMPLETED:
            values.setdefault('done_at', timezone.now())
        values.update(overrides)
        return BackgroundProcess.objects.create(**values)

    def _row(self, process, url='http://retry.example.org/md.xml', **overrides):
        values = dict(
            background_process_id=process.pk,
            reference_key=TemporaryMdMetadataFile.build_reference_key(
                self.service, url),
            requested_url=url,
            described_wms=self.service,
            described_display=self.service.title,
            request_id=timezone.now(),
            state=ReferenceWorkStateEnum.FAILED.value,
            error_kind=ReferenceErrorKind.FETCH_UNREACHABLE.value,
            error_at=OLD,
            import_error='Connection refused')
        values.update(overrides)
        # bulk_create: a save would schedule the very dispatch these tests
        # watch for behind the mutation
        row, = TemporaryMdMetadataFile.objects.bulk_create(
            [TemporaryMdMetadataFile(**values)])
        return row

    def _harvesting_row(self, url='http://retry.example.org/csw-page'):
        """A file of a harvesting run - the flow this retry must never speak to."""
        job = HarvestingJob.objects.create(total_records=1)
        row, = TemporaryMdMetadataFile.objects.bulk_create(
            [TemporaryMdMetadataFile(
                job=job, requested_url=url,
                has_import_error=True, import_error='refused by import')])
        return row

    def _patch(self, row, attributes, client=None):
        return (client or self.anonymous).patch(
            f'/api/registry/harvesting/temporary-md-metadata-file/{row.pk}',
            {"data": {
                "type": "TemporaryMdMetadataFile",
                "id": str(row.pk),
                "attributes": attributes}},
            format=FORMAT,
            HTTP_ACCEPT=JSONAPI)

    def _patch_with_dispatch(self, row, client, attributes=None):
        """A retry PATCH with the row's consumer replaced by a recorder.

        The test case is a ``TransactionTestCase``: the view's save commits
        for real, so the ``on_commit`` of the dispatch already ran when the
        answer stands - no capture of commit callbacks is involved (that is
        a helper of the rolling-back ``TestCase``, not of this one).
        """
        recorder = MagicMock(name='collect_reference')
        with patch.object(service_tasks, 'collect_reference', recorder):
            response = self._patch(
                row, attributes or {'retry': True}, client=client)
        return response, recorder

    # -- the accepted ask -------------------------------------------------

    def test_a_permitted_retry_dispatches_the_reference_task_allow_failed(self):
        """Same row, same process, the one consumer - and the old verdict kept.

        The mutation asks; the claim of the dispatched task decides the
        state, the token and the attempt count. Until that delivery runs,
        the row reads exactly as it did - inspectable with the kind and the
        text which failed it (#1265) - and only the dispatch names the
        ``allow_failed`` authorization of the retry.
        """
        process = self._process()
        row = self._row(process)
        assign_perm('registry.change_webmapservice', self.user, self.service)

        response, collect = self._patch_with_dispatch(row, self.editor)

        self.assertEqual(response.status_code, 200, response.content[:400])
        collect.s.assert_called_once_with(
            background_process_pk=process.pk,
            temporary_md_metadata_file_id=row.pk,
            allow_failed=True)
        collect.s.return_value.set.assert_called_once()
        collect.s.return_value.apply_async.assert_called_once()

        row.refresh_from_db()
        self.assertEqual(ReferenceWorkStateEnum.FAILED.value, row.state)
        self.assertEqual(0, row.attempt_count)
        self.assertEqual(
            ReferenceErrorKind.FETCH_UNREACHABLE.value, row.error_kind)
        self.assertEqual('Connection refused', row.import_error)
        # the ask is not a decision: no counter moved through the api
        process.refresh_from_db()
        self.assertEqual(1, process.references_failed)
        self.assertEqual(0, process.references_stored)

    def test_a_running_run_may_retry_a_failed_reference(self):
        """While the run is still working, a decided row is open to the ask."""
        process = self._process(status=ProcessStatusEnum.RUNNING,
                                done_at=None)
        row = self._row(process)
        assign_perm('registry.change_webmapservice', self.user, self.service)

        response, collect = self._patch_with_dispatch(row, self.editor)

        self.assertEqual(response.status_code, 200, response.content[:400])
        collect.s.assert_called_once()

    def test_the_old_spelling_re_schedule_is_guarded_the_same_way(self):
        """``re_schedule`` reaches the same dispatch, so it meets the same door.

        Unguarded it would re-work a PENDING (skipped) row of a sealed plan
        and move the counters out of the invariant #1263 stores.
        """
        process = self._process()
        pending = self._row(
            process, state=ReferenceWorkStateEnum.PENDING.value,
            error_kind='', error_at=None, import_error='')
        assign_perm('registry.change_webmapservice', self.user, self.service)

        response, collect = self._patch_with_dispatch(
            pending, self.editor, {'reSchedule': True})

        self.assertEqual(response.status_code, 400, response.content[:400])
        collect.s.assert_not_called()

    def test_a_row_of_a_deleted_process_is_gone_and_cannot_be_asked(self):
        """After #1208 retention or an explicit delete, there is nothing to ask."""
        process = self._process()
        row = self._row(process)
        assign_perm('registry.change_webmapservice', self.user, self.service)
        process.delete()

        with patch.object(service_tasks, 'collect_reference',
                          MagicMock()) as collect:
            response = self._patch(row, {'retry': True}, client=self.editor)

        self.assertEqual(response.status_code, 404)
        collect.s.assert_not_called()

    # -- the refused ask --------------------------------------------------

    def test_refuses_a_retry_without_the_permission_of_the_resource(self):
        process = self._process()
        row = self._row(process)
        assign_perm('registry.view_webmapservice', self.user, self.service)

        with patch.object(service_tasks, 'collect_reference',
                          MagicMock()) as collect:
            response = self._patch(row, {'retry': True}, client=self.editor)

        self.assertEqual(response.status_code, 403)
        collect.s.assert_not_called()

    def test_refuses_an_anonymous_retry(self):
        process = self._process()
        row = self._row(process)

        with patch.object(service_tasks, 'collect_reference',
                          MagicMock()) as collect:
            response = self._patch(row, {'retry': True})

        self.assertEqual(response.status_code, 403)
        collect.s.assert_not_called()

    def test_refuses_a_retry_of_a_row_still_planned_or_being_worked(self):
        process = self._process(status=ProcessStatusEnum.RUNNING, done_at=None)
        pending = self._row(
            process, state=ReferenceWorkStateEnum.PENDING.value)
        leased = self._row(
            process, url='http://retry.example.org/md2.xml',
            state=ReferenceWorkStateEnum.LEASED.value,
            lease_expires_at=timezone.now() + timedelta(minutes=5))
        assign_perm('registry.change_webmapservice', self.user, self.service)

        with patch.object(service_tasks, 'collect_reference',
                          MagicMock()) as collect:
            self.assertEqual(
                self._patch(pending, {'retry': True},
                            client=self.editor).status_code, 400)
            self.assertEqual(
                self._patch(leased, {'retry': True},
                            client=self.editor).status_code, 400)
        collect.s.assert_not_called()

    def test_never_reopens_a_failed_or_aborted_run(self):
        for status in (ProcessStatusEnum.FAILED, ProcessStatusEnum.ABORTED):
            process = self._process(status=status)
            row = self._row(process, url=f'http://retry.example.org/{status}')
            assign_perm('registry.change_webmapservice', self.user, self.service)

            with patch.object(service_tasks, 'collect_reference',
                              MagicMock()) as collect:
                response = self._patch(row, {'retry': True},
                                       client=self.editor)

            self.assertEqual(response.status_code, 400, status)
            collect.s.assert_not_called()

    def test_refuses_a_registration_retry_of_a_harvesting_file(self):
        """The harvesting flow reschedules with its run - never through this door."""
        row = self._harvesting_row()
        assign_perm('registry.change_webmapservice', self.user, self.service)

        with patch.object(service_tasks, 'collect_reference',
                          MagicMock()) as collect:
            response = self._patch(row, {'retry': True}, client=self.editor)

        self.assertEqual(response.status_code, 403)
        collect.s.assert_not_called()

    def test_a_retry_asked_as_false_moves_nothing(self):
        process = self._process()
        row = self._row(process)
        assign_perm('registry.change_webmapservice', self.user, self.service)

        response, collect = self._patch_with_dispatch(
            row, self.editor, {'retry': False})

        self.assertEqual(response.status_code, 200, response.content[:400])
        collect.s.assert_not_called()

    # -- what the endpoint must not become --------------------------------

    def test_writes_beyond_the_retry_stay_with_the_model_permission(self):
        """POST and DELETE answer exactly as before: this endpoint creates and
        deletes nothing for a client which only may change a service (#1265)."""
        process = self._process()
        row = self._row(process)
        assign_perm('registry.change_webmapservice', self.user, self.service)

        created = self.editor.post(
            '/api/registry/harvesting/temporary-md-metadata-file',
            {"data": {"type": "TemporaryMdMetadataFile",
                      "attributes": {"requestedUrl": "http://evil/"}}},
            format=FORMAT, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(created.status_code, 403)

        deleted = self.editor.delete(
            f'/api/registry/harvesting/temporary-md-metadata-file/{row.pk}',
            HTTP_ACCEPT=JSONAPI)
        self.assertEqual(deleted.status_code, 403)
        self.assertTrue(TemporaryMdMetadataFile.objects.filter(
            pk=row.pk).exists())

    def test_the_answer_stays_the_work_without_its_permits(self):
        """The retry mutation did not open the claim internals to the answer."""
        process = self._process()
        row = self._row(process)
        assign_perm('registry.change_webmapservice', self.user, self.service)

        response, _ = self._patch_with_dispatch(row, self.editor)

        attributes = response.json()['data']['attributes']
        for secret in ('claim_token', 'lease_expires_at', 'reference_key',
                       'claimToken', 'leaseExpiresAt', 'referenceKey'):
            self.assertNotIn(secret, attributes)
        self.assertEqual(
            str(ReferenceWorkStateEnum.FAILED.value),
            str(attributes['state']))
