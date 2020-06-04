from django.test import TestCase, Client

from MrMap.settings import HOST_NAME, HTTP_OR_SSL, ROOT_URL
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum
from service.helper import service_helper
from structure.models import MrMapUser
from tests.baker_recipes.db_setup import create_superadminuser
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD


class EditorTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        """ Initial creation of objects that are needed during the tests

        Returns:

        """
        # create superuser
        cls.user = create_superadminuser()

        cls.group = cls.user.get_groups().first()

        cls.perm = cls.group.role.permission

        cls.test_wms = {
            "title": "Karte RP",
            "version": OGCServiceVersionEnum.V_1_1_1,
            "type": OGCServiceEnum.WMS,
            "uri": "http://geo5.service24.rlp.de/wms/karte_rp.fcgi?REQUEST=GetCapabilities&VERSION=1.1.1&SERVICE=WMS",
        }

        cls.test_wfs = {
            "title": "Nutzung",
            "version": OGCServiceVersionEnum.V_2_0_0,
            "type": OGCServiceEnum.WFS,
            "uri": "http://geodaten.naturschutz.rlp.de/kartendienste_naturschutz/mod_ogc/wfs_getmap.php?mapfile=group_gdide&REQUEST=GetCapabilities&VERSION=2.0.0&SERVICE=WFS",
        }

        # Since the registration of a service is performed async in an own process, the testing is pretty hard.
        # Therefore in here we won't perform the regular route testing, but rather run unit tests and check whether the
        # important components work as expected.
        # THIS MEANS WE CAN NOT CHECK PERMISSIONS IN HERE; SINCE WE TESTS ON THE LOWER LEVEL OF THE PROCESS

        ## Creating a new wms service model instance
        service = service_helper.create_service(
            cls.test_wms["type"],
            cls.test_wms["version"],
            cls.test_wms["uri"],
            cls.user,
            cls.group
        )
        cls.service_wms = service

        ## Creating a new wfs service model instance
        service = service_helper.create_service(
            cls.test_wfs["type"],
            cls.test_wfs["version"],
            cls.test_wfs["uri"],
            cls.user,
            cls.group
        )
        cls.service_wfs = service

    def _get_logged_out_client(self):
        """ Helping function to encapsulate the logout process

        Returns:
             client (Client): The client object, which holds an active session for the user
        """
        self.client.logout()
        return self.client

    def _get_logged_in_client(self):
        """ Helping function to encapsulate the login process

        Returns:
             client (Client): The client object, which holds an active session for the user
        """
        self.client.login(username=self.user.username, password=PASSWORD)
        return self.client

    def _run_request(self, params: dict, uri: str, request_type: str, client: Client = Client()):
        """ Helping function which performs a request and returns the response

        Args:
            params (dict): The parameters
            uri (str): The request path
            request_type (str): 'post' or 'get', case insensitive
            client (Client): The used client object. Creates a new one if no client is provided
        Returns:
             The response
        """
        request_type = request_type.lower()
        response = None
        if request_type == "get":
            response = client.get(uri, params)
        elif request_type == "post":
            response = client.post(uri, params)
        return response

    def test_edit(self):
        """ Tests the editing functionality

        Returns:

        """
        test_title = "Test"
        test_abstract = "Test"
        test_access_constraints = "Test"

        params = {
            "title": test_title,
            "abstract": test_abstract,
            "access_constraints": test_access_constraints,
        }

        ## case 0: User not logged in -> tries to edit -> fails
        client = Client()
        response = self._run_request(params, "/editor/metadata/{}".format(self.service_wms.metadata.id), "post", client)
        self.service_wms.refresh_from_db()
        self.assertNotEqual(self.service_wms.metadata.title, test_title, msg="Metadata title could be edited by not logged in user!")
        self.assertNotEqual(self.service_wms.metadata.abstract, test_abstract, msg="Metadata abstract could be edited by not logged in user!")
        self.assertNotEqual(self.service_wms.metadata.access_constraints, test_access_constraints, msg="Metadata access constraints could be edited by not logged in user!")

        ## case 1.1: User logged in, has no permission -> tries to edit -> fails
        client = self._get_logged_in_client()

        # manipulate user permissions
        self.perm.can_edit_metadata_service = False
        self.perm.save()

        response = self._run_request(params, "/editor/metadata/{}".format(self.service_wms.metadata.id), "post", client)
        self.service_wms.refresh_from_db()
        self.assertNotEqual(self.service_wms.metadata.title, test_title, msg="Metadata title could be edited by user without permission!")
        self.assertNotEqual(self.service_wms.metadata.abstract, test_abstract, msg="Metadata abstract could be edited by user without permission!")
        self.assertNotEqual(self.service_wms.metadata.access_constraints, test_access_constraints, msg="Metadata access constraints could be edited by user without permission!")

        # restore user permissions
        self.perm.can_edit_metadata_service = True
        self.perm.save()

        ## case 1.2: User logged in -> tries to edit -> success
        client = self._get_logged_in_client()
        response = self._run_request(params, "/editor/metadata/{}".format(self.service_wms.metadata.id), "post", client)
        self.service_wms.refresh_from_db()
        self.service_wms.metadata.refresh_from_db()
        self.assertEqual(self.service_wms.metadata.title, test_title, msg="Metadata title could not be edited by logged in user!")
        self.assertEqual(self.service_wms.metadata.abstract, test_abstract, msg="Metadata abstract could not be edited by logged in user!")
        self.assertEqual(self.service_wms.metadata.access_constraints, test_access_constraints, msg="Metadata access constraints not could be edited by logged in user!")

    def test_restore(self):
        """ Tests the restore functionality

        Returns:

        """
        new_val = "TEST"

        # prepare: Edit title, abstract and keywords
        self.service_wms.metadata.title = new_val
        self.service_wms.metadata.abstract = new_val
        self.service_wms.metadata.keywords.clear()  # removes all keywords
        self.service_wms.metadata.is_custom = True
        self.service_wms.metadata.save()
        self.service_wms.refresh_from_db()

        ## case 0: User not logged in -> tries to restore -> fails
        client = self._get_logged_out_client()
        url = "/editor/restore/{}".format(self.service_wms.metadata.id)
        self._run_request({}, url, "get", client)
        self.assertEqual(self.service_wms.metadata.title, new_val, msg="Metadata was restored by not logged in user!")
        self.assertEqual(self.service_wms.metadata.abstract, new_val, msg="Metadata was restored by not logged in user!")
        self.assertEqual(self.service_wms.metadata.keywords.count(), 0, msg="Metadata was restored by not logged in user!")

        ## case 1.1: User logged in, has no permissions -> tries to restore -> fails
        client = self._get_logged_in_client()

        # manipulate user permissions
        self.perm.can_edit_metadata_service = False
        self.perm.save()

        url = "/editor/restore/{}".format(self.service_wms.metadata.id)

        self._run_request({}, url, "get", client)
        self.assertEqual(self.service_wms.metadata.title, new_val, msg="Metadata was restored by a user without permission!")
        self.assertEqual(self.service_wms.metadata.abstract, new_val, msg="Metadata was restored by a user without permission!")
        self.assertEqual(self.service_wms.metadata.keywords.count(), 0, msg="Metadata was restored by a user without permission!")

        # restore permissions
        self.perm.can_edit_metadata_service = True
        self.perm.save()

        ## case 1.2: User logged in -> tries to restore -> success
        response = self._run_request({}, url, "get", client)
        self.service_wms.metadata.refresh_from_db()
        self.service_wms.refresh_from_db()
        self.assertNotEqual(self.service_wms.metadata.title, new_val, msg="Metadata was not restored by logged in user!")
        self.assertNotEqual(self.service_wms.metadata.abstract, new_val, msg="Metadata was not restored by logged in user!")
        self.assertNotEqual(self.service_wms.metadata.keywords.count(), 0, msg="Metadata was not restored by logged in user!")


