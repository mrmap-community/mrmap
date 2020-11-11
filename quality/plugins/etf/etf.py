import time

import requests
from django_celery_beat.utils import now

from quality.helper.mappingHelper import map_parameters
from quality.models import ConformityCheckConfigurationExternal, \
    ConformityCheckRun
from quality.plugins.etf.etfValidatorClient import EtfValidatorClient
from quality.settings import quality_logger
from service.helper.common_connector import CommonConnector
from service.models import Metadata


class QualityEtf:

    def __init__(self, metadata: Metadata,
                 config: ConformityCheckConfigurationExternal,
                 client: EtfValidatorClient):
        self.metadata = metadata
        self.config = config
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
        document = self.fetch_validation_document()
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
