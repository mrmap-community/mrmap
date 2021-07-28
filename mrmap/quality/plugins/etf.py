"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 27.10.20

"""
import time

import requests
from celery import current_task, states
from django.conf import settings

from quality.helper.mappingHelper import map_parameters
from quality.models import ConformityCheckConfigurationExternal, ConformityCheckRun
from service.helper.common_connector import CommonConnector
from service.models import Metadata
from structure.celery_helper import runs_as_async_task


class EtfClient:

    def __init__(self, url: str):
        self.url = url
        settings.ROOT_LOGGER.info(f"Using ETF url {self.url}")
        self.progress_val = 0
        self.progress_max_val = 1

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
        settings.ROOT_LOGGER.info(f'Uploading document as test object to {url}')
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
        settings.ROOT_LOGGER.info(f'Uploaded test object with id {test_object_id}')
        return test_object_id

    def start_test_run(self, test_config: dict):
        """ Starts a new ETF test run for the given test object and test config.

        Returns:
            str: id of the ETF test run
        """
        settings.ROOT_LOGGER.info(
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
        settings.ROOT_LOGGER.info(
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
        settings.ROOT_LOGGER.info(f'ETF test run status: {val}/{max_val}')
        try:
            self.progress_val = int(val)
            self.progress_max_val = int(max_val)
        except ValueError:
            pass
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
        settings.ROOT_LOGGER.info(f'Deleting ETF test object {url}')
        r = requests.delete(url=url)
        if r.status_code != requests.codes.no_content:
            settings.ROOT_LOGGER.info(
                f'Unexpected HTTP response code {r.status_code} from ETF '
                f'endpoint: {url}')

    def delete_test_run(self, test_run_url: str):
        settings.ROOT_LOGGER.info(f'Deleting ETF test run {test_run_url}')
        r = requests.delete(url=test_run_url)
        if r.status_code != requests.codes.no_content:
            settings.ROOT_LOGGER.info(
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
        settings.ROOT_LOGGER.info(
            f"Retrieving document for validation from {doc_url}")
        connector = CommonConnector(url=doc_url)
        connector.load()
        if connector.status_code != requests.codes.ok:
            raise Exception(
                f"Unexpected HTTP response code {connector.status_code} when "
                f"retrieving document from: {doc_url}")
        return connector.content


class QualityEtf:

    def __init__(self, run: ConformityCheckRun, config_ext: ConformityCheckConfigurationExternal,
                 client: EtfClient):
        self.metadata = run.metadata
        self.config = config_ext
        # TODO support other resource types
        self.resource_url = f'{settings.ROOT_URL}/resourceNew/metadata/datasets/{self.metadata.id}/xml'
        self.check_run = run
        self.client = client
        self.polling_interval_seconds = self.config.polling_interval_seconds
        self.run_url = None

    def run(self) -> ConformityCheckRun:
        """ Runs an ETF check for the associated metadata object.

        Runs the configured ETF suites and updates the associated
        ConformityCheckRun accordingly.
        """
        try:
            test_config = self.create_etf_test_run_config()
            self.run_url = self.client.start_test_run(test_config)
            while not self.client.check_test_run_finished(
                    self.run_url):
                time.sleep(self.polling_interval_seconds)
                self.increase_polling_interval()
                if runs_as_async_task():
                    self.update_progress()
            test_report = self.client.fetch_test_report(self.run_url)
            self.evaluate_test_report(test_report)
        finally:
            self.client.delete_test_run(self.run_url)
        return self.check_run

    def increase_polling_interval(self):
        """Increase the polling interval."""
        new_interval = self.polling_interval_seconds * 2
        if new_interval > self.config.polling_interval_seconds_max:
            new_interval = self.config.polling_interval_seconds_max
        self.polling_interval_seconds = new_interval

    def create_etf_test_run_config(self):
        params = {
            #            "test_object_id": test_object_id,
            "resource_url": self.resource_url,
            "metadata": self.metadata
        }
        return map_parameters(params, self.config.parameter_map)

    def evaluate_test_report(self, test_report):
        """ Evaluates the test report for the given finished ETF test run.

        Updates the ConformityCheckRun accordingly.
        """
        self.check_run.result = test_report
        self.check_run.passed = self.client.is_test_report_passed(test_report)
        self.check_run.save()

    def update_progress(self):
        """Update the progress of the pending task."""
        try:
            max_val = self.client.__getattribute__('progress_max_val')
            val = self.client.__getattribute__('progress_val')
            # We reserve the first 10 percent for the calling method
            progress = 10 + (val / max_val * 100)
            progress = progress if progress <= 90 else 90
            if current_task:
                current_task.update_state(
                    state=states.STARTED,
                    meta={
                        "current": progress,
                    }
                )
        except ZeroDivisionError as e:
            if current_task:
                settings.ROOT_LOGGER.error(
                    f'Could not update pending task with id {current_task.id}. ', e)
