import json

import requests

from quality.settings import quality_logger
from service.helper.common_connector import CommonConnector


class EtfValidatorClient:

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
            error_msg = f'Unexpected HTTP response code {r.status_code} from ETF endpoint.'
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
        quality_logger.info(f'Performing ETF invocation with config {test_config}')
        r = requests.post(url=f'{self.url}v2/TestRuns', json=test_config)
        if r.status_code != 201:
            error_msg = f'Unexpected HTTP response code {r.status_code} from ETF endpoint.'
            try:
                error = r.json()['error']
                error_msg = f'{error_msg} {error}'
            finally:
                raise Exception(error_msg)
        test_run_id = r.json()['EtfItemCollection']['testRuns']['TestRun']['id']
        test_run_url = f'{self.url}v2/TestRuns/{test_run_id}'
        quality_logger.info(f'Started new test run on ETF test suite: {test_run_url}')
        return test_run_url

    def check_test_run_finished(self, test_run_url: str):
        """ Checks if the given ETF test run is finished. """
        r = requests.get(url=f'{test_run_url}/progress')
        if r.status_code != requests.codes.ok:
            raise Exception(f'Unexpected HTTP response code {r.status_code} from ETF endpoint')
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
                f'Unexpected HTTP response code {r.status_code} from ETF endpoint')
        return response

    def is_test_report_passed (self, test_report: dict):
        overall_status = test_report['EtfItemCollection']['testRuns']['TestRun']['status']
        return overall_status == 'PASSED'

    def delete_test_object(self, test_object_id: str):
        url = f'{self.url}v2/TestObjects/{test_object_id}'
        quality_logger.info(f'Deleting ETF test object {url}')
        r = requests.delete(url=url)
        if r.status_code != requests.codes.no_content:
            quality_logger.info(f'Unexpected HTTP response code {r.status_code} from ETF endpoint: {url}')

    def delete_test_run(self, test_run_url: str):
        quality_logger.info(f'Deleting ETF test run {test_run_url}')
        r = requests.delete(url=test_run_url)
        if r.status_code != requests.codes.no_content:
            quality_logger.info(f'Unexpected HTTP response code {r.status_code} from ETF endpoint: {test_run_url}')
