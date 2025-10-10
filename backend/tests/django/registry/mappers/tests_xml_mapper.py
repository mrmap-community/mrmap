from pathlib import Path

from django.test import TestCase
from registry.mappers.persistence import PersistenceHandler
from registry.mappers.xml_mapper import OGCServiceXmlMapper
from registry.models.metadata import ReferenceSystem
from registry.models.service import Layer, WebMapService


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
        crs_expected = [900913, 4839, 4326, 4258, 3857, 3413,
                        31468, 31467, 3045, 3044, 25833, 25832, 1000001]

        self.assertEqual(len(crs_expected), len(db_crs))
        for crs in crs_expected:
            _ = ReferenceSystem(code=str(crs), prefix="EPSG")
            self.assertIn(_, db_crs)

        self.assertEqual(13, db_layers[0].reference_systems.count())
        for crs in crs_expected:
            _ = ReferenceSystem(code=str(crs), prefix="EPSG")
            self.assertIn(_, db_layers[0].reference_systems.all())

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
