"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 27.10.20

"""
import time

import requests
from django_celery_beat.utils import now

from quality.helper.mappingHelper import map_parameters
from quality.models import ConformityCheckConfigurationExternal, \
    ConformityCheckRun
from quality.settings import quality_logger
from service.helper.common_connector import CommonConnector
from service.models import Metadata


class EtfClient:

    def __init__(self, url: str):
        self.url = url
        quality_logger.info(f"Using ETF url {self.url}")

    def upload_test_object(self, document: str):
        """ Uploads the given XML document as ETF test object.

        Args:
            document (str): XML to be uploaded

        Returns:
            str: id of the ETF test object
        """
        files = {'file': ('testobject.xml', document, 'application/xml')}
        data = {'action': 'upload'}
        url = f'{self.url}v2/TestObjects'
        quality_logger.info(f'Uploading document as test object to {url}')
        r = requests.post(url=url, data=data, files=files)
        if r.status_code != requests.codes.ok:
            error_msg = f'Unexpected HTTP response code {r.status_code} from ' \
                        f'ETF endpoint.'
            try:
                error = r.json()['error']
                error_msg = f'{error_msg} {error}'
            finally:
                raise Exception(error_msg)
        r_dict = r.json()
        test_object_id = r_dict['testObject']['id']
        quality_logger.info(f'Uploaded test object with id {test_object_id}')
        return test_object_id

    def start_test_run(self, test_object_id: str, test_config: dict):
        """ Starts a new ETF test run for the given test object and test config.

        Returns:
            str: id of the ETF test run
        """
        quality_logger.info(
            f'Performing ETF invocation with config {test_config}')
        r = requests.post(url=f'{self.url}v2/TestRuns', json=test_config)
        if r.status_code != 201:
            error_msg = f'Unexpected HTTP response code {r.status_code} from ' \
                        f'ETF endpoint.'
            try:
                error = r.json()['error']
                error_msg = f'{error_msg} {error}'
            finally:
                raise Exception(error_msg)
        test_run_id = r.json()['EtfItemCollection']['testRuns']['TestRun']['id']
        test_run_url = f'{self.url}v2/TestRuns/{test_run_id}'
        quality_logger.info(
            f'Started new test run on ETF test suite: {test_run_url}')
        return test_run_url

    def check_test_run_finished(self, test_run_url: str):
        """ Checks if the given ETF test run is finished. """
        r = requests.get(url=f'{test_run_url}/progress')
        if r.status_code != requests.codes.ok:
            raise Exception(
                f'Unexpected HTTP response code {r.status_code} from ETF '
                f'endpoint')
        response_obj = r.json()
        val = response_obj['val']
        max_val = response_obj['max']
        quality_logger.info(f'ETF test run status: {val}/{max_val}')
        return val == max_val

    def fetch_test_report(self, test_run_url: str):
        """ Retrieves the test report for the given finished ETF test run. """
        r = requests.get(url=test_run_url)
        response = r.json()
        if r.status_code != requests.codes.ok:
            raise Exception(
                f'Unexpected HTTP response code {r.status_code} from ETF '
                f'endpoint')
        return response

    def is_test_report_passed(self, test_report: dict):
        overall_status = \
        test_report['EtfItemCollection']['testRuns']['TestRun']['status']
        return overall_status == 'PASSED'

    def delete_test_object(self, test_object_id: str):
        url = f'{self.url}v2/TestObjects/{test_object_id}'
        quality_logger.info(f'Deleting ETF test object {url}')
        r = requests.delete(url=url)
        if r.status_code != requests.codes.no_content:
            quality_logger.info(
                f'Unexpected HTTP response code {r.status_code} from ETF '
                f'endpoint: {url}')

    def delete_test_run(self, test_run_url: str):
        quality_logger.info(f'Deleting ETF test run {test_run_url}')
        r = requests.delete(url=test_run_url)
        if r.status_code != requests.codes.no_content:
            quality_logger.info(
                f'Unexpected HTTP response code {r.status_code} from ETF '
                f'endpoint: {test_run_url}')


class ValidationDocumentProvider:

    def __init__(self, metadata: Metadata,
                 config: ConformityCheckConfigurationExternal):
        self.metadata = metadata
        self.config = config

    def fetch_validation_document(self):
        """ Fetches the XML document that is to be validated.

        Returns:
            str: document to be validated
        """
        validation_target = self.config.validation_target
        doc_url = getattr(self.metadata, validation_target)
        quality_logger.info(
            f"Retrieving document for validation from {doc_url}")
        connector = CommonConnector(url=doc_url)
        connector.load()
        if connector.status_code != requests.codes.ok:
            raise Exception(
                f"Unexpected HTTP response code {connector.status_code} when "
                f"retrieving document from: {doc_url}")
        return connector.content


class QualityEtf:

    def __init__(self, metadata: Metadata,
                 config: ConformityCheckConfigurationExternal,
                 document_provider: ValidationDocumentProvider,
                 client: EtfClient):
        self.metadata = metadata
        self.config = config
        self.document_provider = document_provider
        self.check_run = None
        self.client = client

    def run(self) -> ConformityCheckRun:
        """ Runs an ETF check for the associated metadata object.

        Runs the configured ETF suites and updates the associated
        ConformityCheckRun accordingly.
        """
        self.check_run = ConformityCheckRun.objects.create(
            metadata=self.metadata, conformity_check_configuration=self.config)
        quality_logger.info(f"Created new check run id {self.check_run.pk}")
        document = self.document_provider.fetch_validation_document()
        test_object_id = self.client.upload_test_object(document)
        try:
            test_config = self.create_etf_test_run_config(test_object_id)
            self.check_run.run_url = self.client.start_test_run(test_object_id,
                                                                test_config)
            self.check_run.save()
            while not self.client.check_test_run_finished(
                    self.check_run.run_url):
                time.sleep(self.config.polling_interval_seconds)
            test_report = self.client.fetch_test_report(self.check_run.run_url)
            self.evaluate_test_report(test_report)
        finally:
            self.client.delete_test_run(self.check_run.run_url)
            self.client.delete_test_object(test_object_id)
        return self.check_run

    def create_etf_test_run_config(self, test_object_id):
        params = {
            "test_object_id": test_object_id,
            "metadata": self.metadata
        }
        return map_parameters(params, self.config.parameter_map)

    def evaluate_test_report(self, test_report):
        """ Evaluates the test report for the given finished ETF test run.

        Updates the ConformityCheckRun accordingly.
        """
        self.check_run.result = test_report
        self.check_run.passed = self.client.is_test_report_passed(test_report)
        self.check_run.time_stop = str(now())
        self.check_run.save()
