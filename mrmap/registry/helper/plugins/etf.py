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

from registry.enums.conformity import ReportType
from registry.helper.mapping_helper import map_parameters
from registry.models.conformity import ConformityCheckRun, ConformityCheckConfigurationExternal


class EtfClient:

    def __init__(self, url: str):
        self.url = url
        settings.ROOT_LOGGER.info(f"Using ETF url {self.url}")
        self.progress_val = 0
        self.progress_max_val = 1

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
        if r.status_code != requests.codes.ok:
            raise Exception(
                f'Unexpected HTTP response code {r.status_code} from ETF '
                f'endpoint')
        return r.json()

    def fetch_test_report_html(self, test_run_url: str):
        """ Retrieves the HTML test report for the given finished ETF test run. """
        r = requests.get(url=f'{test_run_url}.html?download=true')
        if r.status_code != requests.codes.ok:
            raise Exception(
                f'Unexpected HTTP response code {r.status_code} from ETF '
                f'endpoint')
        return r.text

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


class QualityEtf:

    def __init__(self, run: ConformityCheckRun, config_ext: ConformityCheckConfigurationExternal,
                 client: EtfClient):
        self.config = config_ext
        self.resource = run.resource
        self.resource_url = settings.ROOT_URL + self.resource.get_xml_view_url()
        self.check_run = run
        self.client = client
        self.polling_interval_seconds = self.config.polling_interval_seconds
        self.run_url = None

    def run(self) -> ConformityCheckRun:
        """ Runs an ETF check on the resource of the associated ConformityCheckRun instance.

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
                if not current_task and current_task.request.id is None:
                    self.update_progress()
            test_report = self.client.fetch_test_report(self.run_url)
            test_report_html = self.client.fetch_test_report_html(self.run_url)
            self.evaluate_test_report(test_report, test_report_html)
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
            "resource_url": self.resource_url,
            "metadata": self.resource
        }
        return map_parameters(params, self.config.parameter_map)

    def evaluate_test_report(self, test_report, test_report_html):
        """ Evaluates the test report for the given finished ETF test run.

        Updates the ConformityCheckRun accordingly.
        """
        self.check_run.report = test_report_html
        self.check_run.report_type = ReportType.HTML.value
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
