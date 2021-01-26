"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 04.05.20

"""
import json
from django.utils import timezone
from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase

from service.helper import service_helper
from service.helper.enums import OGCOperationEnum
from service.models import Metadata, Layer, RequestOperation, AllowedOperation
from service.settings import DEFAULT_SRS
from service.tasks import async_increase_hits, async_activate_service, async_remove_service_task, \
    async_secure_service_task
from structure.models import Organization
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service, create_non_autogenerated_orgas, \
    create_operation
from tests.test_data import get_capabilitites_url

TIMEOUT_MSG_TEMPLATE = "Timeout on async call: {}"


class ServiceTaskTestCase(TestCase):

    def setUp(self):
        self.user = create_superadminuser()
        self.group = self.user.get_groups().first()
        self.metadata = create_wms_service(self.group, how_much_services=10)[0]

        # Declare timeout span
        self.timeout_delta = timezone.timedelta(seconds=10)

        # For new service testing
        create_non_autogenerated_orgas(self.user, 3)
        self.org = Organization.objects.all().first()

        # For securing service
        create_operation(OGCOperationEnum.GET_MAP.value)
        self.operation = RequestOperation.objects.all().first()

    def test_async_increase_hits(self):
        """ Tests the functionality of the asynchronous increasing of hits

        Returns:

        """
        pre_hit_count = self.metadata.hits

        # Perform async hit increasing
        async_increase_hits(self.metadata.id)

        # Get fresh state from db
        self.metadata.refresh_from_db()
        post_hit_count = self.metadata.hits

        fail_msg = "Asynchronous implemented increasing of hits did not work!"
        self.assertNotEqual(pre_hit_count, post_hit_count, fail_msg)
        self.assertEqual(pre_hit_count + 1, post_hit_count, fail_msg)

    def test_async_activate_service(self):
        """ Tests the functionality of the asynchronous activation

        Returns:
        """
        curr_state = self.metadata.is_active
        new_state = not curr_state
        async_activate_service(str(self.metadata.id), self.user.id, new_state)

        self.metadata.refresh_from_db()
        self.assertNotEqual(curr_state, self.metadata.is_active, msg="Async activation did not work for service level.")
        self.assertEqual(new_state, self.metadata.is_active, msg="Async activation did not work for service level.")

        # Check if subelements have been changed as well
        root_layer = Layer.objects.get(
            parent_layer=None,
            parent_service=self.metadata.service
        )
        children = []
        children += list(root_layer.child_layers.all())

        while len(children) > 0:
            # Get child
            child = children.pop()

            # Store child's children in children list
            children += list(child.child_layers.all())
            self.assertNotEqual(curr_state, child.metadata.is_active, msg="Async activation did not work for layer level.")
            self.assertEqual(new_state, child.metadata.is_active, msg="Async activation did not work for layer level.")

    def test_async_new_service(self):
        """ Tests the functionality of the asynchronous new service implementation

        PLEASE NOTE: CURRENTLY NOT USED FOR TESTING

        Returns:
        """
        # Get a valid capabilities url and split it's components into a dict
        urls = get_capabilitites_url()
        url = urls["valid"]
        url_dict = service_helper.split_service_uri(url)

        # Replace the OGCServiceEnum instance with it's value (neede for further process testing)
        url_dict["service"] = url_dict["service"].value

        pre_num_metadatas = Metadata.objects.all().count()

        # ToDo: Outcommented until suitable method has been found to test this celery driven implementation
        #async_new_service(url_dict=url_dict, user_id=self.user.id, register_group_id=self.group.id, register_for_organization_id=None, external_auth=None)
        #post_num_metadatas = Metadata.objects.all().count()
        #self.assertNotEqual(pre_num_metadatas, post_num_metadatas, msg="Asynchronous implementation of new service does not work.")

    def test_async_remove_service(self):
        """ Tests the functionality of the asynchronous removing

        Returns:
        """
        service = self.metadata.service
        async_remove_service_task(service_id=service.id)

        # Try to refresh the metadata, which MUST fail, due to deleted record
        try:
            self.metadata.refresh_from_db()
            self.assertIsNone(self.metadata, msg="Asynchronous removing is not implemented properly. Metadata still exists.")
        except ObjectDoesNotExist:
            self.assertTrue(True)

    def test_async_secure_service_task(self):

        pre_num_secured_oeprations = AllowedOperation.objects.all().count()
        coordinates = [
            [7.117939, 50.501822],
            [7.117939, 50.542],
            [7.194843, 50.542],
            [7.194843, 50.501822],
            [7.117939, 50.501822]
        ]
        polygons = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        coordinates
                    ]
                }
            }]
        }
        geometry = Polygon(coordinates)
        geometry = GEOSGeometry(geometry, DEFAULT_SRS)

        polygons = json.dumps(polygons)

        async_secure_service_task(
            self.metadata.id,
            self.group.id,
            [
                OGCOperationEnum.GET_MAP.value,
            ],
            polygons,
        )

        fail_msg = "SecuredOperation was not created"
        post_num_secured_oeprations = AllowedOperation.objects.all().count()
        self.assertNotEqual(pre_num_secured_oeprations, post_num_secured_oeprations, msg=fail_msg)

        # Try to get the created SecuredOperation record
        try:
            secured_operation = AllowedOperation.objects.get(
                secured_metadata=self.metadata
            )
            self.assertEqual(secured_operation.operation, OGCOperationEnum.GET_MAP.value, msg=fail_msg)
            self.assertEqual(secured_operation.bounding_geometry.area, geometry.area, msg=fail_msg)
            self.assertEqual(secured_operation.bounding_geometry.convex_hull, geometry.convex_hull, msg=fail_msg)
        except ObjectDoesNotExist:
            self.fail(msg=fail_msg)
