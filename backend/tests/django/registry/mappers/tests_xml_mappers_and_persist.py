from collections import defaultdict
from pathlib import Path
from unittest import skip
from uuid import uuid4

from django.test import TestCase
from registry.mappers.persistence import PersistenceHandler
from registry.mappers.xml_mapper import (MDMetadataXmlMapper,
                                         OGCServiceXmlMapper)
from tests.django.test_data.capabilities.csw.expected_service_data import \
    EXPECTED_DATA as EXPECTED_CSW_SERVICE_DATA_2_0_2
from tests.django.test_data.capabilities.wfs.expected_featuretype_data import \
    EXPECTED_DATA as FEATURETYPE_DATA_2_0_0
from tests.django.test_data.capabilities.wfs.expected_service_data import \
    EXPECTED_DATA as EXPECTED_WFS_SERVICE_DATA_2_0_0
from tests.django.test_data.capabilities.wms.expected_layer_data_111 import \
    LAYER_DATA as LAYER_DATA_1_1_1
from tests.django.test_data.capabilities.wms.expected_layer_data_130 import \
    LAYER_DATA as LAYER_DATA_1_3_0
from tests.django.test_data.capabilities.wms.expected_service_data_111 import \
    EXPECTED_DATA as EXPECTED_WMS_SERVICE_DATA_1_1_1
from tests.django.test_data.capabilities.wms.expected_service_data_130 import \
    EXPECTED_DATA as EXPECTED_WMS_SERVICE_DATA_1_3_0
from tests.django.test_data.iso_metadata.expected_dataset_data import \
    EXPECTED_DATA as EXPECTED_DATASET_DATA
from tests.django.test_data.iso_metadata.expected_service_data import \
    EXPECTED_DATA as EXPECTED_SERVICE_DATA


def group_and_accumulate(rows, key_fields, accumulate_fields):
    """
    rows: iterable von Tupeln (z. B. values_list(...))
    key_fields: Liste der Felder, die als Schlüssel dienen
    accumulate_fields: Liste der Felder, deren Werte gesammelt werden sollen
    """
    grouped = defaultdict(lambda: defaultdict(list))

    # --- Gruppieren ---
    for row in rows:
        # row von Tupel -> dict
        row_map = {field: value for field, value in zip(
            key_fields + accumulate_fields, row)}

        key = tuple(row_map[field] for field in key_fields)

        for acc_field in accumulate_fields:
            val = row_map.get(acc_field)
            if val:
                grouped[key][acc_field].append(val)
            else:
                grouped[key][acc_field]

    # --- Rückgabe ---
    result = []

    for key, acc_data in grouped.items():
        if len(accumulate_fields) == 1:
            # nur EIN Akkufeld -> flatten wie im Beispiel
            only_field = accumulate_fields[0]
            result.append((*key, acc_data[only_field]))
        else:
            # mehrere -> dict wie gewohnt
            result.append((*key, {f: acc_data[f] for f in accumulate_fields}))

    return result


class XmlMapperTest(TestCase):

    def __export_parsed_wfs_data(self, data):
        """helper function to generate featuretype specific expected data"""
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

    def __export_parsed_service_data(self, data):
        """helper function to generate service specific expected data"""
        service = data[0]

        # Zuerst alle Operation-URL-Zeilen holen:
        raw_ops = service.operation_urls.values_list(
            "method", "operation", "url", "mime_types__mime_type"
        )

        operation_urls = group_and_accumulate(
            rows=raw_ops,
            key_fields=["method", "operation", "url"],
            accumulate_fields=["mime_types__mime_type"],
        )

        expected_data = {
            "title": service.title,
            "abstract": service.abstract,
            "operation_urls": operation_urls,
            "keywords": list(service.keywords.values_list("keyword", flat=True)),
        }

        import pprint
        from pathlib import Path
        file_path = Path(f"expected_data_{uuid4()}.py")

        # Dictionary als Python-Code in die Datei schreiben
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("EXPECTED_DATA = ")
            f.write(pprint.pformat(expected_data, indent=4))

    def __export_parsed_metadata(self, data):
        """helper function to generate service specific expected data"""
        md = data[0]

        expected_data = {
            "title": md.title,
            "abstract": md.abstract,
            "date_stamp": str(md.date_stamp),
            "access_constraints": md.access_constraints,
            "file_identifier": md.file_identifier,
            "language": md.language,
            "bounding_geometry": md.bounding_geometry.wkt if md.bounding_geometry else None,
            "keywords": list(md.keywords.values_list("keyword", flat=True)),
            "reference_systems": list(md.reference_systems.values_list("code", flat=True)),
        }

        import pprint
        from pathlib import Path
        file_path = Path(f"expected_data_{uuid4()}.py")

        # Dictionary als Python-Code in die Datei schreiben
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("EXPECTED_DATA = ")
            f.write(pprint.pformat(expected_data, indent=4))

    def _call_service_mapper_and_persistence_handler(self):
        """Test that create manager function works correctly."""
        mapper = OGCServiceXmlMapper.from_xml(self.xml)
        self.data = mapper.xml_to_django()
        handler = PersistenceHandler(mapper)
        handler.persist_all()

    def _call_iso_mapper_and_persistence_handler(self):
        """Test that create manager function works correctly."""
        mappers = MDMetadataXmlMapper.from_xml(self.xml)
        self.data = mappers[0].xml_to_django()
        # self.__export_parsed_metadata(self.data)
        handler = PersistenceHandler(mappers[0])
        handler.persist_all()

    def _test_service_success(self, expeced):
        service = self.data[0]

        self.assertEqual(service.title, expeced["title"])
        self.assertEqual(
            service.abstract, expeced["abstract"])

        db_keywords = list(service.keywords.values_list('keyword', flat=True))
        self.assertCountEqual(
            db_keywords, expeced["keywords"], f"SERVICE hat falsche Keywords")

        raw_ops = service.operation_urls.values_list(
            "method", "operation", "url", "mime_types__mime_type"
        )

        operation_urls = group_and_accumulate(
            rows=raw_ops,
            key_fields=["method", "operation", "url"],
            accumulate_fields=["mime_types__mime_type"],
        )

        self.assertCountEqual([(op[0], op[1], op[2], op[3]) for op in operation_urls], [(op[0], op[1], op[2], op[3]) for op in expeced["operation_urls"]],
                              f"SERVICE hat falsche OperationUrls")

        db_metadata_url = list(
            service.remote_metadata.values_list('link', flat=True))
        self.assertCountEqual([str(c) for c in db_metadata_url], [str(c) for c in expeced.get("remote_metadata", [])],
                              f"Service hat falsche RemoteMetadata")

    def _test_md_success(self, expeced):
        md = self.data[0]

        self.assertEqual(md.title, expeced["title"])
        self.assertEqual(md.abstract, expeced["abstract"])
        self.assertEqual(str(md.date_stamp), expeced["date_stamp"])
        self.assertEqual(md.file_identifier, expeced["file_identifier"])
        self.assertEqual(md.language, expeced["language"])

        db_keywords = list(md.keywords.values_list('keyword', flat=True))
        self.assertCountEqual(
            db_keywords, expeced["keywords"], f"MetadataRecord hat falsche Keywords")

        db_categories = list(md.categories.values_list('category', flat=True) if hasattr(md, 'categories') else [])
        self.assertCountEqual(
            db_categories, expeced.get("categories", []), f"MetadataRecord hat falsche Categories")

        db_time_extents = list(extent.__str__() for extent in md.time_extents.all())
        self.assertCountEqual(
            db_time_extents, expeced["time_extents"], f"MetadataRecord hat falsche time extents")

        # ReferenceSystems prüfen
        db_crs = list(
            md.reference_systems.values_list('code', flat=True))
        self.assertCountEqual([str(c) for c in db_crs], [str(c) for c in expeced["reference_systems"]],
                              f"MetadataRecord {md.file_identifier} hat falsche ReferenceSystems")
        


    def _test_wms_success(self, expected):
        wms = self.data[0]

        db_layers = wms.layers.all()

        self.assertEqual(len(expected), len(db_layers))

        for layer in db_layers:
            self.assertIn(layer.identifier, expected,
                          f"Layer {layer.identifier} ist nicht in den erwateten Layern")

            _expected = expected[layer.identifier]

            # Title und Abstract prüfen
            self.assertEqual(
                layer.title, _expected["title"], f"Layer {layer.identifier} hat falschen Title")
            self.assertEqual(
                layer.abstract, _expected["abstract"], f"Layer {layer.identifier} hat falschen Abstract")
            self.assertEqual(
                layer.is_queryable, _expected["is_queryable"], f"Layer {layer.identifier} hat falschen queryable")
            self.assertEqual(
                layer.is_opaque, _expected["is_opaque"], f"Layer {layer.identifier} hat falschen opaque")
            self.assertEqual(
                layer.is_cascaded, _expected["is_cascaded"], f"Layer {layer.identifier} hat falschen cascaded")
            self.assertEqual(
                layer.bbox_lat_lon.wkt if layer.bbox_lat_lon else None, _expected["bbox_lat_lon"], f"Layer {layer.identifier} hat falsche bbox")

            # Keywords prüfen
            db_keywords = list(
                layer.keywords.values_list('keyword', flat=True))
            self.assertCountEqual(
                db_keywords, _expected["keywords"], f"Layer {layer.identifier} hat falsche Keywords")

            # ReferenceSystems prüfen
            db_crs = list(
                layer.reference_systems.values_list('code', flat=True))
            self.assertCountEqual([str(c) for c in db_crs], [str(c) for c in _expected["reference_systems"]],
                                  f"Layer {layer.identifier} hat falsche ReferenceSystems")

            # LayerMetadataUrl prüfen
            db_metadata_url = list(
                layer.remote_metadata.values_list('link', flat=True))
            self.assertCountEqual([str(c) for c in db_metadata_url], [str(c) for c in _expected.get("remote_metadata", [])],
                                  f"Layer {layer.identifier} hat falsche RemoteMetadata")

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

            # FeatureTypeMetadataUrl prüfen
            db_metadata_url = list(
                featuretype.remote_metadata.values_list('link', flat=True))
            self.assertCountEqual([str(c) for c in db_metadata_url], [str(c) for c in expected.get("remote_metadata", [])],
                                  f"FeatureType {featuretype.identifier} hat falsche RemoteMetadata")

    def test_wms_1_1_1(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wms/1.1.1.xml'))
        self._call_service_mapper_and_persistence_handler()
        self._test_service_success(expeced=EXPECTED_WMS_SERVICE_DATA_1_1_1)
        self._test_wms_success(expected=LAYER_DATA_1_1_1)

    def test_wms_1_3_0(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wms/1.3.0.xml'))
        self._call_service_mapper_and_persistence_handler()
        self._test_service_success(expeced=EXPECTED_WMS_SERVICE_DATA_1_3_0)
        self._test_wms_success(expected=LAYER_DATA_1_3_0)

    def test_wfs_2_0_0(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wfs/2.0.0.xml'))
        self._call_service_mapper_and_persistence_handler()
        # self.__export_parsed_wfs_data(self.data[0].featuretypes.all())
        self._test_service_success(expeced=EXPECTED_WFS_SERVICE_DATA_2_0_0)
        self._test_wfs_success()

    def test_csw_2_0_2(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/csw/2.0.2.xml'))
        self._call_service_mapper_and_persistence_handler()
        self._test_service_success(expeced=EXPECTED_CSW_SERVICE_DATA_2_0_2)

    def test_iso_dataset(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/iso_metadata/dataset.xml'))
        self._call_iso_mapper_and_persistence_handler()
        self._test_md_success(expeced=EXPECTED_DATASET_DATA)

    def test_iso_service(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/iso_metadata/service.xml'))
        self._call_iso_mapper_and_persistence_handler()
        self._test_md_success(expeced=EXPECTED_SERVICE_DATA)
