from pathlib import Path

from django.test import TestCase
from registry.mappers.persistence import PersistenceHandler
from registry.mappers.xml_mapper import XmlMapper
from registry.models.metadata import ReferenceSystem
from registry.models.service import Layer, WebMapService

from backend.registry.mappers.configs import XPATH_MAP


class XmlMapperTest(TestCase):

    def test_1_1_1_success(self):
        """Test that create manager function works correctly."""
        db_service = WebMapService.objects.count()

        xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/1.3.0.xml')).resolve().__str__()

        mapper = XmlMapper(
            xml=xml,
            mapping=XPATH_MAP[("WMS", "1.3.0")],
        )

        mapper.xml_to_django()
        handler = PersistenceHandler(mapper)
        handler.persist_all()

        db_service = WebMapService.objects.count()
        self.assertEqual(1, db_service)

        db_layers = Layer.objects.all()
        self.assertEqual(137, len(db_layers))

        db_crs = ReferenceSystem.objects.all()
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
            self.assertIn(_, db_layers[0].reference_systems.all())
