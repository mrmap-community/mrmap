from pathlib import Path

from django.test import TestCase
from registry.mappers.persistence import PersistenceHandler
from registry.mappers.xml_mapper import OGCServiceXmlMapper
from registry.models.metadata import Keyword, ReferenceSystem
from tests.django.registry.mappers.expected_layer_data import \
    DATA as LAYER_DATA


class XmlMapperTest(TestCase):

    def _call_mapper_and_persistence_handler(self):
        """Test that create manager function works correctly."""
        mapper = OGCServiceXmlMapper.from_xml(self.xml)
        self.data = mapper.xml_to_django()
        handler = PersistenceHandler(mapper)
        handler.persist_all()

    def _test_wms_success(self):
        wms = self.data[0]

        db_layers = wms.layers.all()
        self.assertEqual(137, len(db_layers))

        db_crs = ReferenceSystem.objects.filter(layer__in=db_layers).distinct()

        for layer in db_layers:
            self.assertIn(layer.identifier, LAYER_DATA,
                          f"Layer {layer.identifier} ist nicht in den erwateten Layern")

            expected = LAYER_DATA[layer.identifier]

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
        self._call_mapper_and_persistence_handler()
        self._test_wms_success()

    def test_wms_1_3_0(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wms/1.3.0.xml'))
        self._call_mapper_and_persistence_handler()
        self._test_wms_success()

    def _test_wfs_success(self):
        wfs = self.data[0]

        db_featuretypes = wfs.featuretypes.all()
        self.assertEqual(55, len(db_featuretypes))

        db_crs = ReferenceSystem.objects.filter(
            featuretype__in=db_featuretypes).distinct()
        crs_expected = [4258, 4326]

        self.assertEqual(len(crs_expected), len(db_crs))
        for crs in crs_expected:
            _ = ReferenceSystem(code=str(crs), prefix="EPSG")
            self.assertIn(_, db_crs)

        self.assertEqual(1, db_featuretypes[0].reference_systems.count())
        _ = ReferenceSystem(code=str(4258), prefix="EPSG")
        self.assertIn(_, db_featuretypes[0].reference_systems.all())

    def test_wfs_2_0_0(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wfs/2.0.0.xml'))
        self._call_mapper_and_persistence_handler()
        self._test_wfs_success()

    def _test_csw_success(self):
        csw = self.data[0]

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
