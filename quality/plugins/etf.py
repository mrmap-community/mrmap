import json
import time

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

    def run(self):
        self.check_run = ConformityCheckRun.objects.create(
            metadata=self.metadata, conformity_check_configuration=self.config)
        print(f"Created new check run id {self.check_run.pk}")
        test_run_id = self.start_etf_test_run()
        quality_logger.info(f"Started new test run on ETF test suite with id {test_run_id}")
        print(f"Started new test run on ETF test suite with id {test_run_id}")
        self.wait_for_etf_test_run_end(test_run_id)
        self.evaluate_test_report(test_run_id)


    def start_etf_test_run(self):
        etf_config = self.create_etf_test_run_config()
        json_obj = json.dumps(etf_config, indent=4)
        connector = CommonConnector(url="http://localhost:8091/etf-webapp/v2/TestRuns")
        connector.additional_headers["Content-Type"] = "application/json"
        connector.post(json_obj)
        if connector.status_code != 201:
            raise Exception(f"Unexpected HTTP response code from ETF endpoint: {connector.status_code}")
        response = connector.content
        response_obj = json.loads(connector.content)
        test_run_id = response_obj["EtfItemCollection"]["testRuns"]["TestRun"]["id"]
        return test_run_id


    def wait_for_etf_test_run_end(self, test_run_id):
        finished = False
        while not finished:
            connector = CommonConnector(url=f"http://localhost:8091/etf-webapp/v2/TestRuns/{test_run_id}/progress")
            connector.load()
            response = connector.content
            response_obj = json.loads(connector.content)
            val = response_obj["val"]
            maxVal = response_obj["max"]
            print(f"{val}/{maxVal}")
            if val == maxVal:
                finished = True
            time.sleep(2)


    def create_etf_test_run_config(self):

        # capabilities_original_uri
        # service_metadata_original_uri
        # metadata_url

        etf_config = {
            "label": "Test run HUHU",
            "executableTestSuiteIds": [
                "EID59692c11-df86-49ad-be7f-94a1e1ddd8da"
            ],
            "arguments": {
                "files_to_test": ".*",
                "tests_to_execute": ".*"
            },
            "testObject": {
                "resources": {
                    "data": self.metadata.metadata_url
                }
            }
        }
        return etf_config


    def evaluate_test_report(self, test_run_id):
        connector = CommonConnector(url=f"http://localhost:8091/etf-webapp/v2/TestRuns/{test_run_id}")
        connector.load()
        response = connector.content
        response_obj = json.loads(connector.content)
        overall_status = response_obj["EtfItemCollection"]["testRuns"]["TestRun"]["status"]
        print(f"Result: {overall_status}")
        if overall_status == 'PASSED':
            self.check_run.passed = True
        else:
            self.check_run.passed = False
        self.check_run.save()
