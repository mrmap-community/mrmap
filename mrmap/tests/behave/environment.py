import os

from behave.model_core import Status
from behave_django.testcase import BehaviorDrivenTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from MrMap.settings import BASE_DIR, MEDIA_ROOT
from registry.models.metadata import DatasetMetadataRecord
from rest_framework.test import APIClient


def before_all(context):
    # see https://github.com/behave/behave-django/issues/114... fixure behaviour is broken with --simple
    # basicly there are users and groups

    fixtures = ['test_users.json']
    call_command("loaddata", *fixtures, verbosity=0)


def before_feature(context, feature):
    # see https://github.com/behave/behave-django/issues/114... fixure behaviour is broken with --simple
    fixtures = []
    if (
        'MapContext' in feature.name
        or 'OwsContext' in feature.name
        or 'MapContextLayer' in feature.name
    ):
        fixtures.extend(
            ['test_keywords.json', 'test_mapcontext.json', 'test_wms.json'])
    elif 'DatasetMetadataRecord' in feature.name:
        fixtures.extend(['test_keywords.json', 'test_datasetmetadata.json'])
    elif (
        'AllowedWebMapServiceOperation' in feature.name
        or 'WMSGetCapabilitiesResult' in feature.name
        or 'LayerGetMapResult' in feature.name
        or 'LayerGetFeatureInfoResult' in feature.name
        or 'WebMapService' in feature.name
        or 'Layer' in feature.name
    ):
        fixtures.extend(['test_wms.json', 'test_keywords.json'])
    elif (
        'AllowedWebFeatureServiceOperation' in feature.name
        or 'WebFeatureService' in feature.name
        or 'Featuretype' in feature.name
    ):
        fixtures.extend(['test_wfs.json', 'test_keywords.json'])
    elif (
        'HarvestingJob' in feature.name
        or 'CatalogueService' in feature.name
    ):
        fixtures.extend(
            ['test_keywords.json', 'test_datasetmetadata.json', 'test_csw.json'])
    elif 'BackgroundProcess' in feature.name:
        fixtures.extend(['test_background.json'])

    if ('AllowedWebMapServiceOperation' in feature.name
            and 'Related' in feature.name):
        fixtures.extend(['test_wms.json', 'test_allowed_wms_operation.json'])

    if fixtures:
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
    if step.status == Status.failed and hasattr(context, 'response') and context.response:
        print(context.response.content)
