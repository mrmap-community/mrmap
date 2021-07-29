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

from quality.models import ConformityCheckConfigurationExternal, ConformityCheckRun
from quality.plugins.etf import QualityEtf, EtfClient
from resourceNew.models import DatasetMetadata, MetadataContact


class PluginEtfTests(TestCase):
    class EtfValidatorClientMock:

        def start_test_run(self, test_config: dict):
            return "test_run:1"

        def check_test_run_finished(self, test_run_url: str):
            return True

        def fetch_test_report(self, test_run_url: str):
            return {
                "test_report": True
            }

        def fetch_test_report_html(self, test_run_url: str):
            return {
                "test_report": '<html><title>Test report</title></html>'
            }

        def is_test_report_passed(self, test_report: dict):
            return True

        def delete_test_run(self, test_run_url: str):
            pass

    @classmethod
    def setUpTestData(cls):
        cls.etf_client = cls.EtfValidatorClientMock()
        cls.metadata_contact = MetadataContact.objects.create()
        cls.metadata = DatasetMetadata.objects.create(
            title='Testmetadata',
            metadata_contact=cls.metadata_contact,
            dataset_contact=cls.metadata_contact
        )
        cls.config = ConformityCheckConfigurationExternal.objects.create(
            name="Conformance Class: View Service - WMS",
            metadata_types=json.dumps([]),
            conformity_type="etf",
            external_url='http://localhost:8092/validator/',
            parameter_map={
                "label": "Conformance Class: View Service - WMS",
                "arguments": {
                    "files_to_test": ".*",
                    "tests_to_execute": ".*"
                },
                "resources": {
                    "data": "__resource_url"
                },
                "executableTestSuiteIds": [
                    "EIDeec9d674-d94b-4d8d-b744-1309c6cae1d2"
                ]
            }
        )
        cls.check_run = ConformityCheckRun.objects.create(
            metadata=cls.metadata,
            config=cls.config
        )

    def test_run_pass(self):
        etf = QualityEtf(self.check_run, self.config, self.etf_client)
        run = etf.run()
        self.assertTrue(run.passed)
        self.assertTrue(run.result['test_report'])

    def test_run_fail(self):
        etf_client = self.EtfValidatorClientMock()
        etf_client.is_test_report_passed = lambda x: False
        etf = QualityEtf(self.check_run, self.config, etf_client)
        run = etf.run()
        self.assertFalse(run.passed)
        self.assertTrue(run.result['test_report'])


class EtfClientTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.etf_client = EtfClient("http://localhost:8092/validator/")

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
        test_run_url = self.etf_client.start_test_run(test_config)
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
            self.etf_client.start_test_run(test_config)

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
    def test_delete_test_run_ok(self, mock_delete):
        mock_delete.return_value.status_code = requests.codes.no_content
        self.etf_client.delete_test_run('http://localhost:8092/validator/v2/TestRuns/1')

    @patch('quality.plugins.etf.requests.delete')
    def test_delete_test_run_fail(self, mock_delete):
        mock_delete.return_value.status_code = 400
        self.etf_client.delete_test_run('http://localhost:8092/validator/v2/TestRuns/1')
