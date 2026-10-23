from pathlib import Path

from django.test import TestCase
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.mappers.factory import OGCServiceXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler

# The exact advertised tokens of the DWD fixture's operation-wide GetFeature
# outputFormat AllowedValues; spellings must be persisted verbatim because
# GetFeature requests have to send them unchanged.
DWD_GET_FEATURE_FORMATS = [
    "application/gml+xml; version=3.2",
    "GML2",
    "KML",
    "SHAPE-ZIP",
    "application/json",
    "application/vnd.google-earth.kml xml",
    "application/vnd.google-earth.kml+xml",
    "csv",
    "gml3",
    "gml32",
    "json",
    "text/csv",
    "text/javascript",
    "text/xml; subtype=gml/2.1.2",
    "text/xml; subtype=gml/3.1.1",
    "text/xml; subtype=gml/3.2",
]

DWD_XSD_FORMAT = "application/gml+xml; version=3.2"

MAPSERVER_FORMATS = [
    "application/gml+xml; version=3.2",
    "text/xml; subtype=gml/3.2.1",
    "text/xml; subtype=gml/3.1.1",
    "text/xml; subtype=gml/2.1.2",
]


class WfsOperationMimeTypesTest(TestCase):
    """The WFS mapper must store the operation-wide outputFormat AllowedValues
    of the standard AllowedValues wrapper on each operation url row, keep the
    per-feature-type OutputFormats on the feature type, and never invent
    formats for operations that advertise none."""

    def _persist(self, fixture):
        xml = Path(Path.joinpath(Path(__file__).parent.resolve(), f"../../test_data/capabilities/wfs/{fixture}"))
        mapper = OGCServiceXmlMapper.from_xml(xml)
        data = mapper.xml_to_django()
        PersistenceHandler(mapper).persist_all()
        return data[0]

    def _formats(self, service, operation, method=HttpMethodEnum.GET):
        url = service.operation_urls.get(operation=operation.value, method=method.value)
        return list(url.mime_types.values_list("mime_type", flat=True))

    def test_get_feature_formats_are_stored_from_allowed_values(self):
        service = self._persist("2.0.0.xml")
        for method in (HttpMethodEnum.GET, HttpMethodEnum.POST):
            self.assertCountEqual(
                self._formats(service, OGCOperationEnum.GET_FEATURE, method), DWD_GET_FEATURE_FORMATS,
                "GetFeature must store the exact advertised tokens per method row")

    def test_operations_are_owned_by_their_own_advertisement(self):
        service = self._persist("2.0.0.xml")
        self.assertCountEqual(self._formats(service, OGCOperationEnum.DESCRIBE_FEATURE_TYPE), [DWD_XSD_FORMAT])
        self.assertCountEqual(self._formats(service, OGCOperationEnum.GET_PROPERTY_VALUE), [DWD_XSD_FORMAT])
        self.assertCountEqual(
            self._formats(service, OGCOperationEnum.GET_FEATURE_WITH_LOCK), DWD_GET_FEATURE_FORMATS)
        for operation in (OGCOperationEnum.LIST_STORED_QUERIES, OGCOperationEnum.DESCRIBE_STORED_QUERIES,
                          OGCOperationEnum.DROP_STORED_QUERY, OGCOperationEnum.GET_CAPABILITIES):
            self.assertEqual(self._formats(service, operation), [],
                             f"{operation.label} advertises no outputFormat and must store none")

    def test_per_feature_type_formats_stay_on_the_feature_type(self):
        service = self._persist("local_mapserver.2.0.0.xml")
        feature_type = service.featuretypes.get(identifier="ms:Countries")
        self.assertCountEqual(
            list(feature_type.output_formats.values_list("mime_type", flat=True)), MAPSERVER_FORMATS,
            "Per-type OutputFormats must keep their exact advertised spellings")
        self.assertCountEqual(self._formats(service, OGCOperationEnum.GET_FEATURE), MAPSERVER_FORMATS,
                              "The operation-wide list stays separate from the per-type formats")
