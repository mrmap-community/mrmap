"""The harvesting models answer a display string of their own.

The API's ``stringRepresentation`` is ``str(obj)`` and the frontend renders
that field above every other candidate, so a model without ``__str__`` is
labelled with django's plain model repr - ``HarvestingJob object (43)`` -
wherever the app shows the record generically. The registry answers every
other resource as ``<meaningful> (<pk>)``, and the harvesting screens now
answer the same shape: a run names its catalogue and the id of the run, the
log names its message and the id of the log, the schedule names its catalogue
and the id of the schedule (issue #1045).

The same repr used to be interpolated into the media path of a log's extended
description, carrying spaces and parentheses into MEDIA_ROOT and into the url
of the attachment. The path is built from the id of the job alone.
"""
import shutil
import tempfile

from django.test import TestCase, override_settings
from django.urls import reverse
from django_celery_beat.models import CrontabSchedule
from registry.models.harvest import (HarvestingJob, HarvestingLog,
                                     PeriodicHarvestingJob)
from registry.models.metadata import MetadataContact
from registry.models.service import CatalogueService

JSONAPI = "application/vnd.api+json"


class HarvestingDisplayStringTest(TestCase):
    """Shared fixture: one catalogue whose runs, logs and schedule are labelled."""

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Display string contact')
        cls.catalogue = CatalogueService(
            id='22222222-2222-2222-2222-222222222222',
            title='Hamburger Metadatenkatalog', version=202, origin=1,
            service_url='https://example.com/csw',
            metadata_contact=contact, service_contact=contact)
        CatalogueService.objects.bulk_create([cls.catalogue])

    def _attributes(self, name, *args, **query):
        """The attributes of one resource as the json:api endpoint answers them

        Args:
            name: the view name of the endpoint
            *args: the url arguments of the endpoint
            **query: the query parameters of the request

        Returns:
            dict: the attributes of the answered resource
        """
        response = self.client.get(
            reverse(name, args=args), query, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]["attributes"]


class HarvestingJobStrTest(HarvestingDisplayStringTest):
    """A run is labelled by the catalogue it harvests and its own id."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.job = HarvestingJob(service=cls.catalogue)
        # a run without a catalogue is the shadow of a file import
        cls.file_import = HarvestingJob()
        HarvestingJob.objects.bulk_create([cls.job, cls.file_import])

    def test_a_run_names_its_catalogue_and_the_run(self):
        self.assertEqual(
            str(self.job),
            f"Hamburger Metadatenkatalog (harvesting job {self.job.pk})")

    def test_a_file_import_run_without_a_catalogue_names_itself(self):
        """A run without a catalogue has no title to lead with; the label still
        says what its number is the id of"""
        self.assertEqual(str(self.file_import),
                         f"harvesting job {self.file_import.pk}")

    def test_the_api_answers_the_display_string(self):
        for job in (self.job, self.file_import):
            with self.subTest(job=job.pk):
                attributes = self._attributes(
                    "registry:harvestingjob-detail", job.pk,
                    **{"fields[HarvestingJob]": "stringRepresentation"})
                self.assertEqual(
                    attributes["stringRepresentation"], str(job))


class HarvestingLogStrTest(HarvestingDisplayStringTest):
    """A log is labelled by its message and its own id."""

    def test_a_log_names_its_message(self):
        job = HarvestingJob()
        HarvestingJob.objects.bulk_create([job])
        log = job.log(description="GetTotalRecords failed")
        self.assertEqual(str(log), f"GetTotalRecords failed ({log.pk})")

    def test_a_log_without_a_message_names_its_kind(self):
        """The description is blankable; the label never renders empty in
        front of the id"""
        job = HarvestingJob()
        HarvestingJob.objects.bulk_create([job])
        log = HarvestingLog.objects.create(
            harvesting_job=job, description="")
        self.assertEqual(
            str(log), f"{HarvestingLog._meta.verbose_name} ({log.pk})")

    def test_the_api_answers_the_display_string(self):
        job = HarvestingJob()
        HarvestingJob.objects.bulk_create([job])
        log = job.log(description="Response Error")
        attributes = self._attributes(
            "registry:harvestinglog-detail", log.pk,
            **{"fields[HarvestingLog]": "stringRepresentation"})
        self.assertEqual(attributes["stringRepresentation"], str(log))


class HarvestingLogFilepathTest(HarvestingDisplayStringTest):
    """The attachment of a log lands in a directory named by the job's id.

    The path used to interpolate ``str(harvesting_job)``, so the directory
    carried the model repr with its spaces and parentheses into MEDIA_ROOT and
    into the url of the attachment (#1045).
    """

    def setUp(self):
        media = tempfile.mkdtemp(prefix="mrmap-1045-")
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.media = media

    def _write_attachment(self):
        job = HarvestingJob()
        HarvestingJob.objects.bulk_create([job])
        log = job.log(
            description="Response Error",
            extented_description="the response of the remote service")
        return log

    def test_the_directory_is_the_id_of_the_job(self):
        log = self._write_attachment()
        name = log.extented_description.name
        directory, _, rest = name.partition('/')
        job_directory, _, filename = rest.partition('/')
        self.assertEqual(directory, "HarvestingLog")
        self.assertEqual(job_directory, str(log.harvesting_job_id))
        self.assertTrue(filename.endswith('.txt'), name)

    def test_the_path_carries_nothing_but_the_id(self):
        """No space, no parenthesis, no repr: the whole path is stable
        identifiers, whatever the models answer as their display string"""
        name = self._write_attachment().extented_description.name
        self.assertNotIn(' ', name)
        self.assertNotIn('object', name)
        self.assertNotIn('(', name)

    def test_the_attachment_is_readable_from_its_path(self):
        log = self._write_attachment()
        with log.extented_description.open('rb') as attachment:
            self.assertEqual(
                attachment.read(),
                b"the response of the remote service")


class PeriodicHarvestingJobStrTest(HarvestingDisplayStringTest):
    """A schedule is labelled by the catalogue it harvests and its own id."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.crontab = CrontabSchedule.objects.create(minute='0', hour='2')
        cls.schedule = PeriodicHarvestingJob.objects.create(
            service=cls.catalogue, crontab=cls.crontab)

    def test_a_schedule_names_its_catalogue_and_the_schedule(self):
        self.assertEqual(
            str(self.schedule),
            "Hamburger Metadatenkatalog (periodic harvesting job "
            f"{self.schedule.pk})")

    def test_the_endpoint_still_answers_its_schedules(self):
        """The serializer of the schedule answers an explicit subset of
        fields and ``stringRepresentation`` is not among it - widening that
        set is no part of #1045, whose point the model's own display string
        above is. What is pinned here is that the answer of the endpoint is
        unbroken by the display string."""
        response = self.client.get(
            reverse("registry:periodicharvestingjob-list"),
            HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()["data"]
        self.assertEqual(
            [str(self.schedule.pk)],
            [row["id"] for row in rows])
