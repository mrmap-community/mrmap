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
                 base_config: ConformityCheckConfiguration):
        self.metadata = metadata
        self.config = ConformityCheckConfigurationExternal.objects.get(
            pk=base_config.pk)
        self.check_run = None
        self.etf_base_url = self.config.external_url
        quality_logger.info(f"Using ETF base url {self.etf_base_url}")

    def run(self) -> ConformityCheckRun:
        """ Runs an ETF check for the associated metadata object.

        Runs the configured ETF suites of an external check
        and updates the associated ConformityCheckRun accordingly.

        Returns:
            nothing

        """
        self.check_run = ConformityCheckRun.objects.create(
            metadata=self.metadata, conformity_check_configuration=self.config)
        quality_logger.info(f"Created new check run id {self.check_run.pk}")
        test_object_id = self.upload_test_object()
        self.start_remote_test_run(test_object_id)
        self.wait_for_test_run_end()
        self.evaluate_test_run_report()
        # TODO delete test run
        # TODO delete test object
        return self.check_run

    def start_remote_test_run(self, test_object_id):
        """ Starts a new ETF test run for the associated metadata object.

        If successful, it sets the run_url for the associated check run.

        Returns:
            nothing
        """
        etf_config = self.create_etf_test_run_config(test_object_id)
        quality_logger.info(f"Performing ETF invocation with config {etf_config}")
        connector = CommonConnector(url=f"{self.etf_base_url}v2/TestRuns")
        connector.additional_headers["Content-Type"] = "application/json"
        connector.post(etf_config)
        if connector.status_code != 201:
            raise Exception(f"Unexpected HTTP response code from ETF endpoint: {connector.status_code}")
        response = json.loads(connector.content)
        etf_run_id = response["EtfItemCollection"]["testRuns"]["TestRun"]["id"]
        self.check_run.run_url = f"{self.etf_base_url}v2/TestRuns/{etf_run_id}"
        self.check_run.save()
        quality_logger.info(f"Started new test run on ETF test suite with url {self.check_run.run_url}")

    def wait_for_test_run_end(self):
        """ Waits until the associated ETF test run is finished.

        Returns:
            nothing
        """
        finished = False
        while not finished:
            connector = CommonConnector(url=f"{self.check_run.run_url}/progress")
            connector.load()
            if connector.status_code != 200:
                raise Exception(f"Unexpected HTTP response code from ETF endpoint: {connector.status_code}")
            response_obj = json.loads(connector.content)
            val = response_obj["val"]
            max_val = response_obj["max"]
            quality_logger.info(f"ETF test run status: {val}/{max_val}")
            if val == max_val:
                finished = True
            time.sleep(self.config.polling_interval_seconds)

    def create_etf_test_run_config(self, test_object_id):
        # TODO check that metadata parameters work as well
        params = {
            "test_object_id": test_object_id,
            "metadata": self.metadata
        }
        etf_config = map_parameters(params, self.config.parameter_map)
        return json.dumps(etf_config)

    def evaluate_test_run_report(self):
        """ Evaluates the test report for the associated finished ETF test run.

        Also updates the ConformityCheckRun accordingly.

        Returns:
            nothing
        """
        connector = CommonConnector(url=f"{self.check_run.run_url}")
        connector.load()
        response = json.loads(connector.content)
        if connector.status_code != 200:
            raise Exception(f"Unexpected HTTP response code from ETF endpoint: {connector.status_code}")
        overall_status = response["EtfItemCollection"]["testRuns"]["TestRun"]["status"]
        self.check_run.result = response
        self.check_run.time_stop = str(now())
        if overall_status == 'PASSED':
            self.check_run.passed = True
        else:
            self.check_run.passed = False
        self.check_run.save()

    def upload_test_object(self):
        files = {'file': (f'{self.metadata.pk}.xml', self.metadata.get_service_metadata_xml(), 'application/xml')}
        data = {'action': 'upload'}
        # TODO extend CommonConnector to support Form-Multi-Part uploads
        r = requests.post(url=f"{self.etf_base_url}v2/TestObjects", data=data, files=files)
        if r.status_code != requests.codes.ok:
            raise Exception(f"Unexpected HTTP response code from ETF endpoint: {r.status_code}")
        r_dict = r.json()
        test_object_id = r_dict["testObject"]["id"]
        quality_logger.info(f"Uploaded test object with id {test_object_id}")
        return test_object_id
