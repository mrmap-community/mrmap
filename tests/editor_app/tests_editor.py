import os

from django.contrib.auth.hashers import make_password
from django.test import TestCase, Client
from django.utils import timezone

from MapSkinner.settings import HOST_NAME, HTTP_OR_SSL
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum
from service.helper import service_helper
from structure.models import Permission, Role, User, Group


class EditorTestCase(TestCase):

    def setUp(self):
        """ Initial creation of objects that are needed during the tests

        Returns:

        """
        # create superuser
        self.perm = Permission()
        self.perm.name = "_default_"
        for key, val in self.perm.__dict__.items():
            if not isinstance(val, bool) and 'can_' not in key:
                continue
            setattr(self.perm, key, True)
        self.perm.save()

        role = Role.objects.create(
            name="Testrole",
            permission=self.perm,
        )

        self.pw = "test"
        salt = str(os.urandom(25).hex())
        pw = self.pw
        self.user = User.objects.create(
            username="Testuser",
            is_active=True,
            salt=salt,
            password=make_password(pw, salt=salt),
            confirmed_dsgvo=timezone.now(),
        )

        self.group = Group.objects.create(
            name="Testgroup",
            role=role,
            created_by=self.user,
        )

        self.user.groups.add(self.group)

        self.test_wms = {
            "title": "Karte RP",
            "version": OGCServiceVersionEnum.V_1_1_1,
            "type": OGCServiceEnum.WMS,
            "uri": "https://www.geoportal.rlp.de/mapbender/php/mod_showMetadata.php/../wms.php?layer_id=38925&PHPSESSID=7qiruaoul2pdcadcohs7doeu07&withChilds=1",
        }

        # Since the registration of a service is performed async in an own process, the testing is pretty hard.
        # Therefore in here we won't perform the regular route testing, but rather run unit tests and check whether the
        # important components work as expected.
        # THIS MEANS WE CAN NOT CHECK PERMISSIONS IN HERE; SINCE WE TESTS ON THE LOWER LEVEL OF THE PROCESS

        ## Creating a new wms service model instance
        service = service_helper.get_service_model_instance(
            self.test_wms["type"],
            self.test_wms["version"],
            self.test_wms["uri"],
            self.user,
            self.group
        )
        self.raw_data_wms = service.get("raw_data", None)
        self.service_wms = service.get("service", None)

        # persist service without external_auth
        service_helper.persist_service_model_instance(self.service_wms, None)
        self.service_wms.persist_capabilities_doc(self.raw_data_wms.service_capabilities_xml)

    def _get_logged_in_client(self, user: User):
        """ Helping function to encapsulate the login process

        Returns:
             client (Client): The client object, which holds an active session for the user
             user_id (int): The user (id) who shall be logged in
        """
        client = Client()
        user = User.objects.get(
            id=user.id
        )
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        response = client.post("/", data={"username": user.username, "password": self.pw})
        user.refresh_from_db()
        self.assertEqual(response.url, "/home", msg="Redirect wrong")
        self.assertEqual(user.logged_in, True, msg="User not logged in")
        return client

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
            response = client.get(uri, params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
        elif request_type == "post":
            response = client.post(uri, params, HTTP_REFERER=HTTP_OR_SSL + HOST_NAME)
        return response

    def test_edit(self):
        """ Tests the editing functionality

        Returns:

        """
        test_title = "Test"
        test_abstract = "Test"
        test_access_constraints = "Test"
        test_inherit_proxy = True
        test_keywords = "Test1,Test2"
        test_categories = ""

        old_kw_count = self.service_wms.metadata.keywords.count()

        # simply make sure that the number of current keywords is different from the number of new test keywords!
        if old_kw_count == test_keywords.split(","):
            test_keywords += ",Test-X"

        params = {
            "id": self.service_wms.metadata.id,
            "user": self.user,
            "title": test_title,
            "abstract": test_abstract,
            "access_constraints": test_access_constraints,
            "use_proxy_uri": test_inherit_proxy,
            "keywords": test_keywords,
            "categories": test_categories,
        }

        ## case 0: User not logged in -> tries to edit -> fails
        client = Client()
        response = self._run_request(params, "/editor/edit/{}".format(self.service_wms.metadata.id), "post", client)
        self.service_wms.refresh_from_db()
        self.assertNotEqual(self.service_wms.metadata.title, test_title, msg="Metadata title could be edited by not logged in user!")
        self.assertNotEqual(self.service_wms.metadata.abstract, test_abstract, msg="Metadata abstract could be edited by not logged in user!")
        self.assertNotEqual(self.service_wms.metadata.access_constraints, test_access_constraints, msg="Metadata access constraints could be edited by not logged in user!")
        self.assertEqual(self.service_wms.metadata.keywords.count(), old_kw_count, msg="Metadata keywords could be edited by not logged in user!")
        self.assertFalse(self.service_wms.metadata.use_proxy_uri)

        ## case 1.1: User logged in, has no permission -> tries to edit -> fails
        client = self._get_logged_in_client(self.user)

        # manipulate user permissions
        self.perm.can_edit_metadata_service = False
        self.perm.save()

        response = self._run_request(params, "/editor/edit/{}".format(self.service_wms.metadata.id), "post", client)
        self.service_wms.refresh_from_db()
        self.assertNotEqual(self.service_wms.metadata.title, test_title, msg="Metadata title could be edited by user without permission!")
        self.assertNotEqual(self.service_wms.metadata.abstract, test_abstract, msg="Metadata abstract could be edited by user without permission!")
        self.assertNotEqual(self.service_wms.metadata.access_constraints, test_access_constraints, msg="Metadata access constraints could be edited by user without permission!")
        self.assertEqual(self.service_wms.metadata.keywords.count(), old_kw_count, msg="Metadata keywords could be edited by user without permission!")
        self.assertFalse(self.service_wms.metadata.use_proxy_uri)

        # restore user permissions
        self.perm.can_edit_metadata_service = True
        self.perm.save()

        ## case 1.2: User logged in -> tries to edit -> success
        response = self._run_request(params, "/editor/edit/{}".format(self.service_wms.metadata.id), "post", client)
        self.service_wms.refresh_from_db()
        self.assertEqual(self.service_wms.metadata.title, test_title, msg="Metadata title could not be edited by logged in user!")
        self.assertEqual(self.service_wms.metadata.abstract, test_abstract, msg="Metadata abstract could not be edited by logged in user!")
        self.assertEqual(self.service_wms.metadata.access_constraints, test_access_constraints, msg="Metadata access constraints not could be edited by logged in user!")
        self.assertEqual(self.service_wms.metadata.keywords.count(), len(test_keywords.split(",")), msg="Metadata keywords not could be edited by logged in user!")
        self.assertTrue(self.service_wms.metadata.use_proxy_uri)

    def test_restore(self):
        """ Tests the restore functionality

        Returns:

        """
        new_val = "TEST"
        old_title = self.service_wms.metadata.title
        old_abstract = self.service_wms.metadata.abstract
        old_kw_count = self.service_wms.metadata.keywords.count()
        # prepare: Edit title, abstract and keywords
        self.service_wms.metadata.title = new_val
        self.service_wms.metadata.abstract = new_val
        self.service_wms.metadata.keywords.clear()  # removes all keywords
        self.service_wms.metadata.is_custom = True
        self.service_wms.metadata.save()

        ## case 0: User not logged in -> tries to restore -> fails
        client = Client()
        params = {
            "user": self.user,
        }
        url = "/editor/restore/{}".format(self.service_wms.metadata.id)
        self._run_request(params, url, "get", client)
        self.assertEqual(self.service_wms.metadata.title, new_val, msg="Metadata was restored by not logged in user!")
        self.assertEqual(self.service_wms.metadata.abstract, new_val, msg="Metadata was restored by not logged in user!")
        self.assertEqual(self.service_wms.metadata.keywords.count(), 0, msg="Metadata was restored by not logged in user!")

        ## case 1.1: User logged in, has no permissions -> tries to restore -> fails
        client = self._get_logged_in_client(self.user)

        # manipulate user permissions
        self.perm.can_edit_organization = False
        self.perm.save()
        url = "/editor/restore/{}".format(self.service_wms.metadata.id)
        self._run_request(params, url, "get", client)
        self.assertEqual(self.service_wms.metadata.title, new_val, msg="Metadata was restored by a user without permission!")
        self.assertEqual(self.service_wms.metadata.abstract, new_val, msg="Metadata was restored by a user without permission!")
        self.assertEqual(self.service_wms.metadata.keywords.count(), 0, msg="Metadata was restored by a user without permission!")

        # restore permissions
        self.perm.can_edit_organization = True
        self.perm.save()

        ## case 1.2: User logged in -> tries to restore -> success
        self._run_request(params, url, "get", client)
        self.service_wms.metadata.refresh_from_db()
        self.assertEqual(self.service_wms.metadata.title, old_title, msg="Metadata was not restored by logged in user!")
        self.assertEqual(self.service_wms.metadata.abstract, old_abstract, msg="Metadata was not restored by logged in user!")
        self.assertEqual(self.service_wms.metadata.keywords.count(), old_kw_count, msg="Metadata was not restored by logged in user!")


