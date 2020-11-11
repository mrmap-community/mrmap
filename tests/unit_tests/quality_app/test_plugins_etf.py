"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 27.10.20

"""
import json
from unittest.mock import patch

import requests
from django.test import TestCase

from quality.models import ConformityCheckConfigurationExternal
from quality.plugins.etf import QualityEtf, EtfClient
from service.models import Metadata


class PluginEtfTests(TestCase):
    class ValidationDocumentProviderMock:

        def __init__(self, document: str):
            self.document = document

        def fetch_validation_document(self):
            return self.document

    class EtfValidatorClientMock:

        def upload_test_object(self, document: str):
            return "test_object:1"

        def start_test_run(self, test_object_id: str, test_config: dict):
            return "test_run:1"

        def check_test_run_finished(self, test_run_url: str):
            return True

        def fetch_test_report(self, test_run_url: str):
            return {
                "test_report": True
            }

        def is_test_report_passed(self, test_report: dict):
            return True

        def delete_test_object(self, test_object_id: str):
            pass

        def delete_test_run(self, test_run_url: str):
            pass

    @classmethod
    def setUpTestData(cls):
        cls.etf_client = cls.EtfValidatorClientMock()
        cls.metadata = Metadata.objects.create(
            title='Testmetadata',
        )
        cls.document_provider = cls.ValidationDocumentProviderMock('<MOCK_VALIDATION_DOCUMENT/>')
        cls.config = ConformityCheckConfigurationExternal.objects.create(
            name="Conformance Class: View Service - WMS",
            metadata_types=json.dumps([]),
            conformity_type="etf",
            external_url='http://localhost:8092/validator/',
            validation_target='capabilities_uri',
            parameter_map={
                "label": "Conformance Class: View Service - WMS",
                "arguments": {
                    "files_to_test": ".*",
                    "tests_to_execute": ".*"
                },
                "testObject": {
                    "id": "__test_object_id"
                },
                "executableTestSuiteIds": [
                    "EIDeec9d674-d94b-4d8d-b744-1309c6cae1d2"
                ]
            }
        )

    def test_run_pass(self):
        etf = QualityEtf(self.metadata, self.config, self.document_provider, self.etf_client)
        run = etf.run()
        self.assertTrue(run.passed)
        self.assertTrue(run.result['test_report'])
        self.assertIsNotNone(run.time_stop)

    def test_run_fail(self):
        etf_client = self.EtfValidatorClientMock()
        etf_client.is_test_report_passed = lambda x: False
        etf = QualityEtf(self.metadata, self.config, self.document_provider, etf_client)
        run = etf.run()
        self.assertFalse(run.passed)
        self.assertTrue(run.result['test_report'])
        self.assertIsNotNone(run.time_stop)


class EtfClientTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.etf_client = EtfClient("http://localhost:8092/validator/")

    @patch('quality.plugins.etf.requests.post')
    def test_upload_test_object_ok(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'testObject': {
                'id': 1
            }
        }
        test_object_id = self.etf_client.upload_test_object("<upload_document/>")
        self.assertEquals(test_object_id, 1)

    @patch('quality.plugins.etf.requests.post')
    def test_upload_test_object_fail(self, mock_post):
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {
            'error': 'Upload failed'
        }
        expected_message = 'Unexpected HTTP response code 400 from ETF endpoint. Upload failed'
        with self.assertRaisesMessage(Exception, expected_message=expected_message):
            self.etf_client.upload_test_object("<upload_document/>")

    @patch('quality.plugins.etf.requests.post')
    def test_start_test_run_ok(self, mock_post):
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {
            'EtfItemCollection': {
                'testRuns': {
                    'TestRun': {
                        'id': 1
                    }
                }
            }
        }
        test_config = {}
        test_run_url = self.etf_client.start_test_run(1, test_config)
        self.assertEquals(test_run_url, 'http://localhost:8092/validator/v2/TestRuns/1')

    @patch('quality.plugins.etf.requests.post')
    def test_start_test_run_fail(self, mock_post):
        mock_post.return_value.status_code = 400
        mock_post.return_value.json.return_value = {
            'error': 'Upload failed'
        }
        expected_message = 'Unexpected HTTP response code 400 from ETF endpoint. Upload failed'
        with self.assertRaisesMessage(Exception, expected_message=expected_message):
            test_config = {}
            self.etf_client.start_test_run(1, test_config)

    @patch('quality.plugins.etf.requests.get')
    def test_check_test_run_finished_ok_finished(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'max': 20,
            'val': 20
        }
        self.assertTrue(self.etf_client.check_test_run_finished('http://localhost:8092/validator/v2/TestRuns/1'))

    @patch('quality.plugins.etf.requests.get')
    def test_check_test_run_finished_ok_not_finished(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'max': 20,
            'val': 5
        }
        self.assertFalse(self.etf_client.check_test_run_finished('http://localhost:8092/validator/v2/TestRuns/1'))

    @patch('quality.plugins.etf.requests.get')
    def test_check_test_run_finished_fail(self, mock_get):
        mock_get.return_value.status_code = 500
        expected_message = 'Unexpected HTTP response code 500 from ETF endpoint'
        with self.assertRaisesMessage(Exception, expected_message=expected_message):
            self.etf_client.check_test_run_finished('http://localhost:8092/validator/v2/TestRuns/1')

    @patch('quality.plugins.etf.requests.get')
    def test_fetch_test_reports_ok(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            'EtfItemCollection': {
                'testRuns': {
                    'TestRun': {
                        'id': 1
                    }
                }
            }
        }
        self.assertTrue(self.etf_client.fetch_test_report('http://localhost:8092/validator/v2/TestRuns/1'))

    @patch('quality.plugins.etf.requests.get')
    def test_fetch_test_reports_fail(self, mock_get):
        mock_get.return_value.status_code = 500
        expected_message = 'Unexpected HTTP response code 500 from ETF endpoint'
        with self.assertRaisesMessage(Exception, expected_message=expected_message):
            self.etf_client.fetch_test_report('http://localhost:8092/validator/v2/TestRuns/1')

    def test_is_test_report_passed_true(self):
        test_report = {
            'EtfItemCollection': {
                'testRuns': {
                    'TestRun': {
                        'status': 'PASSED'
                    }
                }
            }
        }
        self.assertTrue(self.etf_client.is_test_report_passed(test_report))

    def test_is_test_report_passed_false(self):
        test_report = {
            'EtfItemCollection': {
                'testRuns': {
                    'TestRun': {
                        'status': 'FAILED'
                    }
                }
            }
        }
        self.assertFalse(self.etf_client.is_test_report_passed(test_report))

    @patch('quality.plugins.etf.requests.delete')
    def test_delete_test_object_ok(self, mock_delete):
        mock_delete.return_value.status_code = requests.codes.no_content
        self.etf_client.delete_test_object("1")

    @patch('quality.plugins.etf.requests.delete')
    def test_delete_test_object_fail(self, mock_delete):
        mock_delete.return_value.status_code = 400
        self.etf_client.delete_test_object("1")

    @patch('quality.plugins.etf.requests.delete')
    def test_delete_test_run_ok(self, mock_delete):
        mock_delete.return_value.status_code = requests.codes.no_content
        self.etf_client.delete_test_run('http://localhost:8092/validator/v2/TestRuns/1')

    @patch('quality.plugins.etf.requests.delete')
    def test_delete_test_run_fail(self, mock_delete):
        mock_delete.return_value.status_code = 400
        self.etf_client.delete_test_run('http://localhost:8092/validator/v2/TestRuns/1')
