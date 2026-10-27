from django.test import SimpleTestCase
from registry.ows_lib.csw.csw import CatalogueServiceClient


class CatalogueServiceClientAdvertisedMaxRecordsTest(SimpleTestCase):
    """the maxRecords limit of the GetRecords constraints is a hint which harvesting reads
    before it asks the service itself (#694)"""

    def make_client(self, constraints):
        capabilities = f"""
            <Capabilities version="2.0.2" xmlns="http://www.opengis.net/cat/csw/2.0.2"
                xmlns:ows="http://www.opengis.net/ows/1.1">
                <ows:OperationsMetadata><ows:Operation name="GetRecords">
                    {constraints}
                </ows:Operation></ows:OperationsMetadata>
            </Capabilities>
        """.encode()
        return CatalogueServiceClient(capabilities)

    def test_named_max_records_constraint_is_answered(self):
        client = self.make_client(
            '<ows:Constraint name="MaxRecords"><ows:Value>100</ows:Value></ows:Constraint>')
        self.assertEqual(client.advertised_max_records(), 100)

    def test_spelling_with_namespace_prefix_is_found(self):
        client = self.make_client(
            '<ows:Constraint name="csw:maxRecords"><ows:Value>25</ows:Value></ows:Constraint>')
        self.assertEqual(client.advertised_max_records(), 25)

    def test_service_without_the_constraint_answers_none(self):
        client = self.make_client(
            '<ows:Constraint name="SupportedISOQueryables">'
            '<ows:Value>apiso:Abstract</ows:Value></ows:Constraint>')
        self.assertIsNone(client.advertised_max_records())

    def test_non_numeric_value_is_no_limit(self):
        client = self.make_client(
            '<ows:Constraint name="MaxRecords"><ows:Value>unbounded</ows:Value></ows:Constraint>')
        self.assertIsNone(client.advertised_max_records())

    def test_limit_of_another_operation_is_not_the_get_records_limit(self):
        client = CatalogueServiceClient("""
            <Capabilities version="2.0.2" xmlns="http://www.opengis.net/cat/csw/2.0.2"
                xmlns:ows="http://www.opengis.net/ows/1.1">
                <ows:OperationsMetadata>
                    <ows:Operation name="GetRecords"></ows:Operation>
                    <ows:Operation name="GetCapabilities">
                        <ows:Constraint name="MaxRecords"><ows:Value>10</ows:Value></ows:Constraint>
                    </ows:Operation>
                </ows:OperationsMetadata>
            </Capabilities>
        """.encode())
        self.assertIsNone(client.advertised_max_records())
