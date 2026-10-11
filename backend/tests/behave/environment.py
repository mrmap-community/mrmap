from behave.model_core import Status
from behave_django.testcase import BehaviorDrivenTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from MrMap.settings import BASE_DIR
from registry.models.metadata import DatasetMetadataRecord
from rest_framework.test import APIClient

#: Prefix of the feature tag that requests one fixture file, e.g. ``@fixtures:test_wms.json``.
FIXTURE_TAG_PREFIX = "fixtures:"

#: Tag of a feature that needs no data at all beyond the users ``before_all`` loads.
NO_FIXTURES_TAG = "no_fixtures"


def before_all(context):
    # see https://github.com/behave/behave-django/issues/114... fixure behaviour is broken with --simple
    # basicly there are users and groups

    fixtures = ['test_users.json']
    call_command("loaddata", *fixtures, verbosity=0)


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


def before_feature(context, feature):
    """Load the data a feature declared with its tags.

    The order of the ``@fixtures:`` tags is the order ``loaddata`` reads them in, which is what
    resolves foreign keys between fixture files; keep it if you edit the tags.
    """
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


def before_scenario(context, scenario):
    # https://github.com/behave/behave-django/issues/77

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
