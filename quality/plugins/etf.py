import json
import time

import requests
from django_celery_beat.utils import now

from quality.helper.mappingHelper import map_parameters
from quality.models import ConformityCheckConfigurationExternal, ConformityCheckRun, ConformityCheckConfiguration
from quality.settings import quality_logger
from service.helper.common_connector import CommonConnector
from service.models import Metadata


class QualityEtf:

    def __init__(self, metadata: Metadata,
                 base_config: ConformityCheckConfiguration,
                 cookies: [str]):
        self.metadata = metadata
        self.config = ConformityCheckConfigurationExternal.objects.get(
            pk=base_config.pk)
        self.check_run = None
        self.etf_base_url = self.config.external_url
        self.cookies = cookies
        quality_logger.info(f"Using ETF base url {self.etf_base_url} with cookies {self.cookies}")

    def run(self) -> ConformityCheckRun:
        """ Runs an ETF check for the associated metadata object.

        Runs the configured ETF suites of an external check
        and updates the associated ConformityCheckRun accordingly.
        """
        self.check_run = ConformityCheckRun.objects.create(
            metadata=self.metadata, conformity_check_configuration=self.config)
        quality_logger.info(f"Created new check run id {self.check_run.pk}")
        document = self.fetch_validation_document()
        test_object_id = self.upload_test_object(document)
        self.start_remote_test_run(test_object_id)
        self.wait_for_test_run_end()
        self.evaluate_test_run_report()
        # TODO delete test run
        # TODO delete test object
        return self.check_run

    def fetch_validation_document(self):
        """ Fetches the XML document that is to be validated.

        Returns:
            str: document to be validated
        """
        validation_target = self.config.validation_target
        doc_url = getattr(self.metadata, validation_target)
        quality_logger.info(f"Retrieving document for validation from {doc_url}")
        r = requests.get(doc_url, cookies=self.cookies)
        if r.status_code != requests.codes.ok:
            raise Exception(
                f"Unexpected HTTP response code {r.status_code} when retrieving document from: {doc_url}")
        return r.text

    def upload_test_object(self, document):
        """ Uploads the given XML document as ETF test object.

        Args:
            document (str): XML to be uploaded

        Returns:
            str: id of the ETF test object
        """
        files = {'file': (f'{self.metadata.pk}.xml', document, 'application/xml')}
        data = {'action': 'upload'}
        url = f"{self.etf_base_url}v2/TestObjects"
        r = requests.post(url=url, data=data, files=files)
        if r.status_code != requests.codes.ok:
            error_msg = f"Unexpected HTTP response code {r.status_code} from ETF endpoint."
            try:
                error = r.json()['error']
                error_msg = f"{error_msg} {error}"
            finally:
                raise Exception(error_msg)
        r_dict = r.json()
        test_object_id = r_dict["testObject"]["id"]
        quality_logger.info(f"Uploaded test object with id {test_object_id}")
        return test_object_id

    def start_remote_test_run(self, test_object_id):
        """ Starts a new ETF test run for the associated metadata object.

        If successful, it sets the run_url for the associated check run.
        """
        etf_config = self.create_etf_test_run_config(test_object_id)
        quality_logger.info(f"Performing ETF invocation with config {etf_config}")
        connector = CommonConnector(url=f"{self.etf_base_url}v2/TestRuns")
        connector.additional_headers["Content-Type"] = "application/json"
        connector.post(etf_config)
        if connector.status_code != 201:
            error_msg = f"Unexpected HTTP response code {connector.status_code} from ETF endpoint."
            try:
                error = json.loads(connector.content)['error']
                error_msg = f"{error_msg} {error}"
            finally:
                raise Exception(error_msg)
        response = json.loads(connector.content)
        etf_run_id = response["EtfItemCollection"]["testRuns"]["TestRun"]["id"]
        self.check_run.run_url = f"{self.etf_base_url}v2/TestRuns/{etf_run_id}"
        self.check_run.save()
        quality_logger.info(f"Started new test run on ETF test suite with url {self.check_run.run_url}")

    def wait_for_test_run_end(self):
        """ Waits until the associated ETF test run is finished. """
        finished = False
        while not finished:
            connector = CommonConnector(url=f"{self.check_run.run_url}/progress")
            connector.load()
            if connector.status_code != 200:
                raise Exception(f"Unexpected HTTP response code {connector.status_code} from ETF endpoint")
            response_obj = json.loads(connector.content)
            val = response_obj["val"]
            max_val = response_obj["max"]
            quality_logger.info(f"ETF test run status: {val}/{max_val}")
            if val == max_val:
                finished = True
            time.sleep(self.config.polling_interval_seconds)

    def create_etf_test_run_config(self, test_object_id):
        params = {
            "test_object_id": test_object_id,
            "metadata": self.metadata
        }
        etf_config = map_parameters(params, self.config.parameter_map)
        return json.dumps(etf_config)

    def evaluate_test_run_report(self):
        """ Evaluates the test report for the associated finished ETF test run.

        Also updates the ConformityCheckRun accordingly.
        """
        connector = CommonConnector(url=f"{self.check_run.run_url}")
        connector.load()
        response = json.loads(connector.content)
        if connector.status_code != 200:
            raise Exception(
                f"Unexpected HTTP response code {connector.status_code} from ETF endpoint: {self.check_run.run_url}")
        overall_status = response["EtfItemCollection"]["testRuns"]["TestRun"]["status"]
        self.check_run.result = response
        self.check_run.time_stop = str(now())
        if overall_status == 'PASSED':
            self.check_run.passed = True
        else:
            self.check_run.passed = False
        self.check_run.save()

    def cleanup_etf_resources(self):
        pass
