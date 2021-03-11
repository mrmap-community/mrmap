from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.exceptions import ValidationError
from django.test import TestCase

from MrMap.validators import geometry_is_empty


class ValidatorsTestCase(TestCase):

    def test_geometry_is_empty_with_empty_geometry(self):
        """IF an empty GEOSGeometry object should be validated, THEN the validator shall raise a ValidationError with the message 'Empty geometry collections are not allowed.'."""
        raised = False
        try:
            geometry_is_empty(MultiPolygon())
        except ValidationError as e:
            raised = True
            self.assertEqual('Empty geometry collections are not allowed.', e.message, msg='ValidationError message is not as expacted.')
        finally:
            self.assertIs(True, raised, msg='ValidationError didn\'t raised')

    def test_geometry_is_empty_with_non_empty_geometry(self):
        """IF an non empty GEOSGeometry object should be validated, THEN the validator shall not raise a ValidationError."""
        p1 = Polygon(((0, 0), (0, 1), (1, 1), (0, 0)))
        p2 = Polygon(((1, 1), (1, 2), (2, 2), (1, 1)))
        raised = False
        try:
            geometry_is_empty(MultiPolygon(p1, p2))
        except ValidationError:
            raised = True
        finally:
            self.assertIs(False, raised, msg='ValidationError didn\'t raised')
