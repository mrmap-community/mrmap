from behave.model_core import Status
from behave_django.testcase import BehaviorDrivenTestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from MrMap.settings import BASE_DIR
from registry.models.harvest import HarvestingJob, PeriodicHarvestingJob
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, MetadataContact,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueService
from rest_framework.test import APIClient

#: Prefix of the feature tag that requests one fixture file, e.g. ``@fixtures:test_wms.json``.
FIXTURE_TAG_PREFIX = "fixtures:"

#: Tag of a feature that needs no data at all beyond the users ``before_all`` loads.
NO_FIXTURES_TAG = "no_fixtures"

# rows which only the application record features of #830 declare; the pks belong
# to test_applicationmetadata.json and test_applicationharvesting.json
APPLICATION_CONTACT_PKS = [1235, 1236]
APPLICATION_RECORD_PKS = [
    "a11c0000-0000-4000-8000-000000000001",
    "a11c0000-0000-4000-8000-000000000002",
]
APPLICATION_HARVESTING_JOB_PKS = [903]

#: Fixture file adding the service and application records of the #829 mixed
#: ``/csw`` set to the dataset set the ``/csw`` features share.
MIXED_RECORDS_FIXTURE = 'test_csw_mixed_records.json'

#: Pks of the two records that file declares (see the file itself).
MIXED_RECORDS_PKS = (
    'f4ac83a9-3d1e-4b2f-9c6a-9f2e7d1c5b0a',
    'c0ffee00-7a11-4c1d-8f2b-3e9d5a2b6c01',
)

#: Fixture file with the harvesting runs, logs, files and schedules of #1080.
HARVESTING_STATES_FIXTURE = 'test_harvesting_states.json'

#: The two catalogues whose cascade is everything the file adds beyond the
#: contact and the crontab; both carry the ``1080`` marker of the file.
HARVESTING_STATES_SERVICES = (
    'aaaa1080-0000-4000-8000-00000000000a',
    'bbbb1080-0000-4000-8000-00000000000b',
)

#: Pks of the two schedules and their crontab; the child rows of the
#: multi-table inheritance go before the celery rows they hang on.
HARVESTING_STATES_PERIODIC_PKS = (1080502, 1080503)
HARVESTING_STATES_CRONTAB_PK = 1080501
HARVESTING_STATES_CONTACT_PK = 1080401


def before_all(context):
    # see https://github.com/behave/behave-django/issues/114... fixure behaviour is broken with --simple
    # basicly there are users and groups

    fixtures = ['test_users.json']
    call_command("loaddata", *fixtures, verbosity=0)
    # Remember which users that seeded: ``before_feature`` resolves the natural keys of
    # every feature fixture against these rows, so their absence names a run that
    # truncated the database between scenarios (see ``assert_seeded_users``).
    context.seeded_user_pks = set(get_user_model().objects.values_list("pk", flat=True))


def assert_seeded_users(context, where):
    """Refuse a run whose runner truncated the rows the hooks seeded.

    ``manage.py behave`` without ``--simple`` runs a scenario in behave-django's
    ``BehaviorDrivenTestCase``, which is a ``TransactionTestCase`` and therefore flushes
    the whole database when the scenario ends. The fixtures of this suite are loaded once
    per feature in ``before_feature`` and are not restored, so everything after that flush
    asks an empty database: the sibling scenarios of the feature fail on missing rows and
    the next feature aborts with ``HOOK-ERROR in before_feature``, because ``loaddata``
    resolves its natural keys against the users of ``before_all``.

    The suite is standardized on ``--simple``, whose ``TestCase`` rolls a scenario back
    instead of flushing; it is an option of the ``behave`` management command rather than
    of behave itself, so no ``behave.ini`` can carry it as a default. Say so here, where a
    run that walks into the trap would otherwise read as broken fixtures.
    """
    seeded = getattr(context, "seeded_user_pks", None)
    if not seeded:
        # ``--dry-run`` skips every environment hook, so there is nothing to compare to
        return
    if get_user_model().objects.filter(pk__in=seeded).count() == len(seeded):
        return
    raise AssertionError(
        f"{where}: the users that before_all loaded are gone, so this run truncated the "
        f"database since they were seeded. That is the flush of the default runner; the "
        f"fixtures of this suite are loaded once per feature and never restored, so only "
        f"the runner of --simple, which rolls a scenario back instead of flushing, runs "
        f"them. The behave service of docker-compose.dev.yml, CI and every command of "
        f"tests/behave/AGENTS.md pass that flag; a hand written run does too:\n"
        f"    python manage.py behave --simple --noinput --keepdb <feature path>")


def requested_fixtures(feature):
    """Fixture files that the ``@fixtures:<file>.json`` tags of a feature request."""
    return [tag[len(FIXTURE_TAG_PREFIX):]
            for tag in getattr(feature, "tags", [])
            if tag.startswith(FIXTURE_TAG_PREFIX)]


def load_fixtures(fixtures):
    call_command("loaddata", *fixtures, verbosity=0)

    if 'test_datasetmetadata.json' in fixtures:
        # fix dataset xml files
        rbsn_rr_file = open(
            f"{BASE_DIR}/tests/django/test_data/RBSN_RR.xml", mode="rb")
        rbsn_rr_bytes = rbsn_rr_file.read()
        rbsn_rr = DatasetMetadataRecord.objects.get(
            pk="d8b50d33-2ad7-4a41-bd0d-2d518ea10fd4")
        rbsn_rr.xml_backup_file = SimpleUploadedFile(
            'md_metadata.xml', rbsn_rr_bytes)
        rbsn_rr.save()
        rbsn_rr_file.close()

        rbsn_rh_file = open(
            f"{BASE_DIR}/tests/django/test_data/RBSN_RH.xml", mode="rb")
        rbsn_rh_bytes = rbsn_rh_file.read()
        rbsn_rh = DatasetMetadataRecord.objects.get(
            pk="9e57ada9-d3bf-403f-bd6c-eb4d38f0ef8e")
        rbsn_rh.xml_backup_file = SimpleUploadedFile(
            'md_metadata.xml', rbsn_rh_bytes)
        rbsn_rh.save()
        rbsn_rh_file.close()

    if MIXED_RECORDS_FIXTURE in fixtures:
        # the service and application records of the mixed #829 set carry their
        # stored document as a file the same way the dataset records above do,
        # so the fixture names a path and the document is attached here
        _attach_backup(ServiceMetadataRecord,
                       'f4ac83a9-3d1e-4b2f-9c6a-9f2e7d1c5b0a',
                       'tests/django/test_data/csw/mixed_service_dienst-1.xml')
        _attach_backup(ApplicationMetadataRecord,
                       'c0ffee00-7a11-4c1d-8f2b-3e9d5a2b6c01',
                       'tests/django/test_data/csw/mixed_application_anwendung-1.xml')


def _attach_backup(model, pk, relative_document_path):
    """Write a stored document onto a metadata record loaded from a fixture.

    Same fix the dataset records already owe: a fixture names a file but cannot
    ship its content, and the ``/csw`` response reads the stored document, so
    the file is attached right after ``loaddata``.
    """
    with open(f"{BASE_DIR}/{relative_document_path}", mode="rb") as document:
        record = model.objects.get(pk=pk)
        record.xml_backup_file = SimpleUploadedFile(
            'md_metadata.xml', document.read())
        record.save()


def before_feature(context, feature):
    """Load the data a feature declared with its tags.

    The order of the ``@fixtures:`` tags is the order ``loaddata`` reads them in, which is what
    resolves foreign keys between fixture files; keep it if you edit the tags.
    """
    assert_seeded_users(context, f"before_feature of {feature.filename}")
    requested = requested_fixtures(feature)
    if NO_FIXTURES_TAG in getattr(feature, "tags", []):
        if requested:
            raise AssertionError(
                f"{feature.filename}: @no_fixtures contradicts the requested {requested}")
        return
    if not requested:
        raise AssertionError(
            f"{feature.filename}: declare one @fixtures:<file>.json tag per fixture, or "
            f"@{NO_FIXTURES_TAG} if the scenarios really need no rows. Loading nothing used to "
            f"happen silently whenever a title did not match the legacy mapping, and a feature "
            f"without data passes on 'meta.pagination.count == 0' without testing anything.")
    load_fixtures(requested)


def after_feature(context, feature):
    """Undo the rows a fixture-tagged feature added for its siblings.

    A feature's fixtures are loaded once and not restored for its siblings,
    and the counts which the sibling ``/csw`` features assert name exactly the
    two dataset records of the shared set -- so the service and application
    records of ``test_csw_mixed_records.json`` have to be gone as soon as the
    feature which asked for them is done. Its own scenarios only see them
    while it runs.
    """
    fixtures = requested_fixtures(feature)
    if "test_applicationharvesting.json" in fixtures:
        # deleting the job cascades the harvested relations which hang from it
        HarvestingJob.objects.filter(pk__in=APPLICATION_HARVESTING_JOB_PKS).delete()
    if "test_applicationmetadata.json" in fixtures:
        # the record cascades its own harvested relations; the contact is what
        # RESTRICTs a deletion, so it goes last
        ApplicationMetadataRecord.objects.filter(pk__in=APPLICATION_RECORD_PKS).delete()
        MetadataContact.objects.filter(pk__in=APPLICATION_CONTACT_PKS).delete()
    if MIXED_RECORDS_FIXTURE in fixtures:
        for pk in MIXED_RECORDS_PKS:
            ServiceMetadataRecord.objects.filter(pk=pk).delete()
            ApplicationMetadataRecord.objects.filter(pk=pk).delete()
    if HARVESTING_STATES_FIXTURE in fixtures:
        # the same rule for the harvesting set of #1080: its three runs are in
        # the very phases the sibling features' counts of test_csw.json do not
        # carry, so leaving them behind moves those counts. The catalogues
        # cascade their runs, and the runs cascade logs and temporary files;
        # the schedules go by hand because deleting the child row of the
        # multi-table inheritance leaves its celery parent row where it is.
        PeriodicHarvestingJob.objects.filter(
            pk__in=HARVESTING_STATES_PERIODIC_PKS).delete()
        PeriodicTask.objects.filter(
            pk__in=HARVESTING_STATES_PERIODIC_PKS).delete()
        CrontabSchedule.objects.filter(
            pk=HARVESTING_STATES_CRONTAB_PK).delete()
        CatalogueService.objects.filter(
            pk__in=HARVESTING_STATES_SERVICES).delete()
        MetadataContact.objects.filter(
            pk=HARVESTING_STATES_CONTACT_PK).delete()


def before_scenario(context, scenario):
    # https://github.com/behave/behave-django/issues/77

    assert_seeded_users(
        context, f"before_scenario of {scenario.filename}:{scenario.line}")
    BehaviorDrivenTestCase.port = 8000
    context.client = APIClient()
    context.query_params = {}
    context.patchers = []


def after_scenario(context, scenario):
    for patcher in context.patchers:
        patcher.stop()


def after_step(context, step):
    """Dump what a failing or erroring step got back, so that the scenario explains itself."""
    if step.status not in (Status.failed, Status.error):
        return

    response = getattr(context, 'response', None)
    if not response:
        return

    print(f"failing step: {step.name}  # {step.filename}:{step.line}")
    content_type = response.get('Content-Type', '')
    print(f"response: {response.status_code} {content_type}")
    if 'text/html' in content_type:
        # the browsable API renderer answered, its page is noise here
        print("hint: the response is HTML and not JSON; the scenario needs the request header"
              " HTTP_ACCEPT with the value application/vnd.api+json")
        return
    print(response.content)
