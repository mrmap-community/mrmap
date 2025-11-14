from collections import defaultdict
from pathlib import Path
from uuid import uuid4

from django.test import TestCase
from registry.mappers.persistence import PersistenceHandler
from registry.mappers.xml_mapper import OGCServiceXmlMapper
from registry.models.metadata import Keyword
from tests.django.test_data.capabilities.wfs.expected_featuretype_data import \
    EXPECTED_DATA as FEATURETYPE_DATA_2_0_0
from tests.django.test_data.capabilities.wms.expected_layer_data_111 import \
    LAYER_DATA as LAYER_DATA_1_1_1
from tests.django.test_data.capabilities.wms.expected_layer_data_130 import \
    LAYER_DATA as LAYER_DATA_1_3_0


class XmlMapperTest(TestCase):

    def __export_parsed_wfs_data(self, data):
        expected_layer_data = {
            item.identifier: {
                "title": item.title,
                "abstract": item.abstract,
                "bbox_lat_lon": item.bbox_lat_lon.wkt if item.bbox_lat_lon else None,
                "output_formats": list(item.output_formats.values_list("mime_type", flat=True)),
                "keywords": list(item.keywords.values_list("keyword", flat=True)),
                "reference_systems": list(item.reference_systems.values_list("code", flat=True)),
            }
            for item in data
        }

        import pprint
        from pathlib import Path
        file_path = Path(f"expected_data_{uuid4()}.py")

        # Dictionary als Python-Code in die Datei schreiben
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("EXPECTED_DATA = ")
            f.write(pprint.pformat(expected_layer_data, indent=4))

    def __export_parsed_csw_data(self, data):
        csw = data[0]

        # Zuerst alle Operation-URL-Zeilen holen:
        raw_ops = csw.operation_urls.values_list(
            "method", "operation", "url", "mime_types__mime_type"
        )

        # Jetzt gruppieren:
        grouped = defaultdict(lambda: defaultdict(list))

        for method, operation, url, mime in raw_ops:
            if mime:
                grouped[(method, operation, url)]["mime_types"].append(mime)
            else:
                # Sicherstellen, dass der Key existiert und später eine leere Liste bleibt
                grouped[(method, operation, url)]

        # Danach wieder in eine Liste überführen:
        operation_urls = [
            (method, operation, url, op_data["mime_types"])
            for (method, operation, url), op_data in grouped.items()
        ]

        expected_data = {
            "title": csw.title,
            "abstract": csw.abstract,
            "operation_urls": operation_urls,
            "keywords": list(csw.keywords.values_list("keyword", flat=True)),
        }

        import pprint
        from pathlib import Path
        file_path = Path(f"expected_data_{uuid4()}.py")

        # Dictionary als Python-Code in die Datei schreiben
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("EXPECTED_DATA = ")
            f.write(pprint.pformat(expected_data, indent=4))

    def _call_mapper_and_persistence_handler(self):
        """Test that create manager function works correctly."""
        mapper = OGCServiceXmlMapper.from_xml(self.xml)
        self.data = mapper.xml_to_django()
        handler = PersistenceHandler(mapper)
        handler.persist_all()

    def _test_wms_success(self):
        wms = self.data[0]

        db_layers = wms.layers.all()

        self.assertEqual(len(self.layer_data), len(db_layers))

        for layer in db_layers:
            self.assertIn(layer.identifier, self.layer_data,
                          f"Layer {layer.identifier} ist nicht in den erwateten Layern")

            expected = self.layer_data[layer.identifier]

            # Title und Abstract prüfen
            self.assertEqual(
                layer.title, expected["title"], f"Layer {layer.identifier} hat falschen Title")
            self.assertEqual(
                layer.abstract, expected["abstract"], f"Layer {layer.identifier} hat falschen Abstract")
            self.assertEqual(
                layer.is_queryable, expected["is_queryable"], f"Layer {layer.identifier} hat falschen queryable")
            self.assertEqual(
                layer.is_opaque, expected["is_opaque"], f"Layer {layer.identifier} hat falschen opaque")
            self.assertEqual(
                layer.is_cascaded, expected["is_cascaded"], f"Layer {layer.identifier} hat falschen cascaded")
            self.assertEqual(
                layer.bbox_lat_lon.wkt if layer.bbox_lat_lon else None, expected["bbox_lat_lon"], f"Layer {layer.identifier} hat falsche bbox")

            # Keywords prüfen
            db_keywords = list(
                layer.keywords.values_list('keyword', flat=True))
            self.assertCountEqual(
                db_keywords, expected["keywords"], f"Layer {layer.identifier} hat falsche Keywords")

            # ReferenceSystems prüfen
            db_crs = list(
                layer.reference_systems.values_list('code', flat=True))
            self.assertCountEqual([str(c) for c in db_crs], [str(c) for c in expected["reference_systems"]],
                                  f"Layer {layer.identifier} hat falsche ReferenceSystems")

    def test_wms_1_1_1(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wms/1.1.1.xml'))
        self.layer_data = LAYER_DATA_1_1_1
        self._call_mapper_and_persistence_handler()
        self._test_wms_success()

    def test_wms_1_3_0(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wms/1.3.0.xml'))
        self.layer_data = LAYER_DATA_1_3_0
        self._call_mapper_and_persistence_handler()
        self._test_wms_success()

    def _test_wfs_success(self):
        wfs = self.data[0]
        db_featuretypes = wfs.featuretypes.all()

        self.assertEqual(len(FEATURETYPE_DATA_2_0_0), len(db_featuretypes))

        for featuretype in db_featuretypes:
            self.assertIn(featuretype.identifier, FEATURETYPE_DATA_2_0_0,
                          f"FeatureType {featuretype.identifier} ist nicht in den erwateten FeatureTypes")

            expected = FEATURETYPE_DATA_2_0_0[featuretype.identifier]

            # Title und Abstract prüfen
            self.assertEqual(
                featuretype.title, expected["title"], f"FeatureType {featuretype.identifier} hat falschen Title")
            self.assertEqual(
                featuretype.abstract, expected["abstract"], f"FeatureType {featuretype.identifier} hat falschen Abstract")
            self.assertEqual(
                featuretype.bbox_lat_lon.wkt if featuretype.bbox_lat_lon else None, expected["bbox_lat_lon"], f"FeatureType {featuretype.identifier} hat falsche bbox")

            # Keywords prüfen
            db_keywords = list(
                featuretype.keywords.values_list('keyword', flat=True))
            self.assertCountEqual(
                db_keywords, expected["keywords"], f"FeatureType {featuretype.identifier} hat falsche Keywords")

            # ReferenceSystems prüfen
            db_crs = list(
                featuretype.reference_systems.values_list('code', flat=True))
            self.assertCountEqual([str(c) for c in db_crs], [str(c) for c in expected["reference_systems"]],
                                  f"FeatureType {featuretype.identifier} hat falsche ReferenceSystems")

    def test_wfs_2_0_0(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wfs/2.0.0.xml'))
        self._call_mapper_and_persistence_handler()
        self._test_wfs_success()

    def _test_csw_success(self):
        csw = self.data[0]
        self.__export_parsed_csw_data(self.data)

        db_keywords = Keyword.objects.filter(
            catalogueservice_metadata=csw).distinct()
        keywords_expected = ["catalogue", "discovery", "metadata"]

        self.assertEqual(len(keywords_expected), len(db_keywords))
        for keyword in keywords_expected:
            _ = Keyword(keyword=keyword)
            self.assertIn(_.keyword, keywords_expected)

    def test_csw_2_0_2(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/csw/2.0.2.xml'))
        self._call_mapper_and_persistence_handler()
        self._test_csw_success()
