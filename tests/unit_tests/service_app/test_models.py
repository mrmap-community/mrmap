from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.test import TestCase

from service.models import AllowedOperation, Metadata, Service, Layer, FeatureType
from tests.baker_recipes.db_setup import create_wms_service, create_superadminuser, create_wfs_service


class AllowedOperationTestModel(TestCase):

    def setUp(self):
        self.user = create_superadminuser()
        self.root_metadata = create_wms_service(group=self.user.get_groups.first(),
                                                how_much_sublayers=100,
                                                how_much_services=1)[0]

    def test_validation_error_on_bounding_geometry_is_empty(self):
        """IF a AllowedOperation object with an empty geometry is prepeard for saving with the full_clean() method, THEN the AllowedOperation object shall raise a ValidationError for the bounding_geometry field."""
        raised = False
        try:
            allowed_operation = AllowedOperation(allowed_area=MultiPolygon(), root_metadata=self.root_metadata)
            allowed_operation.full_clean()
        except ValidationError as e:
            raised = True
            self.assertIn('allowed_area', e.message_dict,
                          msg='There is no ValidationError for field `allowed_area`.')
        finally:
            self.assertIs(True, raised, msg='ValidationError didn\'t raised')

    def test_object_with_validation_errors_shall_not_be_stored(self):
        """IF a AllowedOperation object with an empty geometry should be saved, THEN the AllowedOperation object shall not be stored to the database."""
        allowed_operation = AllowedOperation(allowed_area=MultiPolygon(), root_metadata=self.root_metadata)
        print(allowed_operation.allowed_area)
        print(allowed_operation.allowed_area.empty)
        try:
            allowed_operation.save()
            print('saved')
        except:
            pass
        finally:
            self.assertFalse(AllowedOperation.objects.all().exists(),
                             msg='The AllowedOperation table shall be empty after trying to save empty geometry data.')

    def test_save_successfully(self):
        """IF a valid AllowedOperation object should be saved, THEN the AllowedOperation object shall be stored to the database with correct secured_metadata relations."""
        p1 = Polygon(((0, 0), (0, 1), (1, 1), (0, 0)))
        p2 = Polygon(((1, 1), (1, 2), (2, 2), (1, 1)))
        allowed_operation = AllowedOperation(allowed_area=MultiPolygon(p1, p2), root_metadata=self.root_metadata)
        allowed_operation.save()
        self.assertEqual(1, AllowedOperation.objects.all().count(),
                         msg='The AllowedOperation table shall be contains exactly 1 object.')

        allowed_operation.refresh_from_db()

        self.assertEqual(list(allowed_operation.secured_metadata.all().order_by('id')),
                         list(allowed_operation.root_metadata.get_descendant_metadatas(include_self=True).order_by('id')),
                         msg='The secured_metadata field shall contains all children of the root_metadata field.')


class MetadataTestCase(TestCase):

    def setUp(self):
        self.user = create_superadminuser()
        self.wms_metadata = create_wms_service(group=self.user.get_groups.first(),
                                               how_much_sublayers=10,
                                               how_much_services=2)
        self.wfs_metadata = create_wfs_service(group=self.user.get_groups.first(),
                                               how_much_featuretypes=10,
                                               how_much_services=2)

    def test_wms_delete(self):
        """
            If the delete of a given Metadata without dependencies is called, the related Service, all Layer, and Layer Metdata objects shall be deleted.

            Dependencies in this context are multiple relations from Metadata objects to one Dataset Metadata object.
            The Dataset Metadata object with more than one reverse pointed relations will not be deleted.
        """
        metadata = self.wms_metadata[0]
        service = metadata.service
        sub_elements = metadata.service.get_subelements().select_related('metadata')

        metadata.delete()

        try:
            Metadata.objects.get(pk=metadata.pk)
            raise AssertionError('Metadata still exist')
        except ObjectDoesNotExist:
            pass

        try:
            Service.objects.get(pk=service.pk)
            raise AssertionError('Service still exist')
        except ObjectDoesNotExist:
            pass

        for sub_element in sub_elements:
            try:
                Metadata.objects.get(pk=sub_element.metadata.pk)
                raise AssertionError('Metadata of sub element still exist')
            except ObjectDoesNotExist:
                pass
            try:
                Layer.objects.get(pk=sub_element.pk)
                raise AssertionError('Layer still exist')
            except ObjectDoesNotExist:
                pass

    def test_wfs_delete(self):
        """
            If the delete of a given Metadata without dependencies is called, the related Service, all FeatureType, and FeatureType Metdata objects shall be deleted.

            Dependencies in this context are multiple relations from Metadata objects to one Dataset Metadata object.
            The Dataset Metadata object with more than one reverse pointed relations will not be deleted.
        """
        metadata = self.wfs_metadata[0]
        service = metadata.service
        sub_elements = metadata.service.get_subelements().select_related('metadata')

        metadata.delete()

        try:
            Metadata.objects.get(pk=metadata.pk)
            raise AssertionError('Metadata still exist')
        except ObjectDoesNotExist:
            pass

        try:
            Service.objects.get(pk=service.pk)
            raise AssertionError('Service still exist')
        except ObjectDoesNotExist:
            pass

        for sub_element in sub_elements:
            try:
                Metadata.objects.get(pk=sub_element.metadata.pk)
                raise AssertionError('Metadata of sub element still exist')
            except ObjectDoesNotExist:
                pass
            try:
                FeatureType.objects.get(pk=sub_element.pk)
                raise AssertionError('FeatureType still exist')
            except ObjectDoesNotExist:
                pass
