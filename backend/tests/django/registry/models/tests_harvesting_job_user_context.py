"""The user context of a service-less harvesting run (issue #1278).

A run without a catalogue is the file import: it is started by the deployment
itself, no request stands behind it and its history names no user, so its
internal task context falls back to the superuser the deployment seeded. The
name of that account belongs to the deployment, not to the code - the run has
to resolve it from the configured value (``settings.MRMAP_USER``) and saving
the first file of such a run must not depend on a username hardcoded in the
code.
"""

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from registry.enums.harvesting import HarvestingPhaseEnum
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile

DEPLOYMENT_ADMIN = "deployment-admin"


class ServiceLessJobUserContextTest(TestCase):
    """A service-less run names its user from the deployment, not from the code."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        # a database as an earlier deployment left it: the test database may
        # carry the superuser post_migrate seeded from MRMAP_USER=mrmap; this
        # test removes it, so nothing can resolve a user by that name anymore
        get_user_model().objects.filter(username="mrmap").delete()
        self.admin = get_user_model().objects.create_user(
            username=DEPLOYMENT_ADMIN)
        self.job = HarvestingJob.objects.create(
            total_records=1, phase=HarvestingPhaseEnum.RECORDS_TO_DB)

    def test_saving_the_first_file_resolves_the_configured_admin(self):
        with override_settings(MRMAP_USER=DEPLOYMENT_ADMIN,
                               MEDIA_ROOT=self.media_root):
            file = TemporaryMdMetadataFile(job=self.job)
            file.md_metadata_file.save(
                "record.xml", ContentFile(b"<record/>"), save=False)
            # this save answered User.DoesNotExist before #1278: it asked for
            # the user "mrmap" of a deployment which does not have one
            file.save()
            self.assertTrue(
                TemporaryMdMetadataFile.objects.filter(pk=file.pk).exists())
            # the file's task and every later task of the run name the account
            # the deployment configured, not a name from the code
            self.assertEqual(self.admin.pk,
                             self.job._http_request()["user_pk"])
