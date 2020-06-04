from django.test import TestCase, Client

from MrMap.settings import HOST_NAME, GENERIC_NAMESPACE_TEMPLATE
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum, OGCOperationEnum
from service.helper import service_helper, xml_helper
from service.models import Document
from service.tasks import async_process_secure_operations_form
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

        cls.cap_doc_wms = Document.objects.get(
            related_metadata=cls.service_wms.metadata
        )
        cls.cap_doc_wfs = Document.objects.get(
            related_metadata=cls.service_wfs.metadata
        )

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

    def test_proxy_setting(self):
        """ Tests whether the proxy can be set properly.

        Returns:
        """
        metadata = self.service_wms.metadata

        # To avoid running celery in a separate test instance, we do not call the route. Instead we call the logic, which
        # is used to process access settings directly.
        params = {
            "use_proxy": "on",
            "log_proxy": "on",
        }
        async_process_secure_operations_form(params, metadata.id)

        self.cap_doc_wms.refresh_from_db()
        doc_unsecured = self.cap_doc_wms.original_capability_document
        doc_secured = self.cap_doc_wms.current_capability_document

        # Check for all operations if the uris has been changed!
        # Do not check for GetCapabilities, since we always change this uri during registration!
        # Make sure all versions can be matched by the code - the xml structure differs a lot from version to version
        service_version = metadata.get_service_version()

        if metadata.is_service_type(OGCServiceEnum.WMS):
            operations = [
                OGCOperationEnum.GET_MAP.value,
                OGCOperationEnum.GET_FEATURE_INFO.value,
                OGCOperationEnum.DESCRIBE_LAYER.value,
                OGCOperationEnum.GET_LEGEND_GRAPHIC.value,
                OGCOperationEnum.GET_STYLES.value,
                OGCOperationEnum.PUT_STYLES.value,
            ]
        elif metadata.is_service_type(OGCServiceEnum.WFS):
            operations = [
                OGCOperationEnum.GET_FEATURE.value,
                OGCOperationEnum.TRANSACTION.value,
                OGCOperationEnum.LOCK_FEATURE.value,
                OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value,
            ]
        else:
            operations = []

        # create xml documents from string documents and fetch only the relevant <Request> element for each
        xml_unsecured = xml_helper.parse_xml(doc_unsecured)
        request_unsecured = xml_helper.try_get_single_element_from_xml(elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Request"), xml_elem=xml_unsecured)
        xml_secured = xml_helper.parse_xml(doc_secured)
        request_secured = xml_helper.try_get_single_element_from_xml(elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("Request"), xml_elem=xml_secured)

        for operation in operations:
            # Get <OPERATION> element
            operation_unsecured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format(operation), request_unsecured)
            operation_secured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format(operation), request_secured)

            if service_version == OGCServiceVersionEnum.V_1_0_0:
                if metadata.is_service_type(OGCServiceEnum.WMS):
                    # The WMS 1.0.0 specification uses <OPERATION> instead of <GetOPERATION> for any operation element.
                    operation = operation.replace("Get", "")

                    # Get <OPERATION> element again
                    operation_unsecured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format(operation), request_unsecured)
                    operation_secured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format(operation), request_secured)

                # Version 1.0.0 holds the uris in the "onlineResource" attribute of <Get> and <Post>
                get_unsecured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get"), operation_unsecured)
                get_secured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get"), operation_secured)
                post_unsecured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post"), operation_unsecured)
                post_secured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post"), operation_secured)

                online_res = "onlineResource"
                get_unsecured = xml_helper.try_get_attribute_from_xml_element(get_unsecured, online_res)
                get_secured = xml_helper.try_get_attribute_from_xml_element(get_secured, online_res)
                post_unsecured = xml_helper.try_get_attribute_from_xml_element(post_unsecured, online_res)
                post_secured = xml_helper.try_get_attribute_from_xml_element(post_secured, online_res)

                # Assert that all get/post elements are not None
                self.assertIsNotNone(get_secured, msg="The secured uri of '{}' is None!".format(operation))
                self.assertIsNotNone(post_secured, msg="The secured uri of '{}' is None!".format(operation))

                # Assert that the secured version is different from the unsecured one
                self.assertNotEqual(get_unsecured, get_secured, msg="The uri of '{}' has not been secured!".format(operation))
                self.assertNotEqual(post_unsecured, post_secured, msg="The uri of '{}' has not been secured!".format(operation))

                # Assert that the HOST_NAME constant appears in the secured uri
                self.assertContains(get_secured, HOST_NAME)
                self.assertContains(post_secured, HOST_NAME)

            elif service_version == OGCServiceVersionEnum.V_1_1_0 \
                    or service_version == OGCServiceVersionEnum.V_2_0_0 \
                    or service_version == OGCServiceVersionEnum.V_2_0_2:
                # Only WFS
                # Get <OPERATION> element again, since the operation is now identified using an attribute, not an element tag
                operation_unsecured = xml_helper.try_get_single_element_from_xml(
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation") + "[@name='" + operation + "']",
                    request_unsecured
                )
                operation_secured = xml_helper.try_get_single_element_from_xml(
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation") + "[@name='" + operation + "']",
                    request_secured
                )

                # Version 1.1.0 holds the uris in the href attribute of <Get> and <Post>
                get_unsecured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get"), operation_unsecured)
                get_secured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get"), operation_secured)
                post_unsecured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post"), operation_unsecured)
                post_secured = xml_helper.try_get_single_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post"), operation_secured)

                get_unsecured = xml_helper.get_href_attribute(get_unsecured)
                get_secured = xml_helper.get_href_attribute(get_secured)
                post_unsecured = xml_helper.get_href_attribute(post_unsecured)
                post_secured = xml_helper.get_href_attribute(post_secured)

                # Assert that all get/post elements are not None
                self.assertIsNotNone(get_secured, msg="The secured uri of '{}' is None!".format(operation))
                self.assertIsNotNone(post_secured, msg="The secured uri of '{}' is None!".format(operation))

                # Assert that the secured version is different from the unsecured one
                self.assertNotEqual(get_unsecured, get_secured, msg="The uri of '{}' has not been secured!".format(operation))
                self.assertNotEqual(post_unsecured, post_secured, msg="The uri of '{}' has not been secured!".format(operation))

                # Assert that the HOST_NAME constant appears in the secured uri
                self.assertContains(get_secured, HOST_NAME)
                self.assertContains(post_secured, HOST_NAME)

            elif service_version == OGCServiceVersionEnum.V_1_1_1 or service_version == OGCServiceVersionEnum.V_1_3_0:
                # Version 1.1.1 holds the uris in the <OnlineResource> element inside <Get> and <Post>
                get_unsecured = xml_helper.try_get_single_element_from_xml(
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    operation_unsecured
                )
                get_secured = xml_helper.try_get_single_element_from_xml(
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Get")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    operation_secured
                )
                post_unsecured = xml_helper.try_get_single_element_from_xml(
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    operation_unsecured
                )
                post_secured = xml_helper.try_get_single_element_from_xml(
                    ".//" + GENERIC_NAMESPACE_TEMPLATE.format("Post")
                    + "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    operation_secured
                )

                get_unsecured = xml_helper.get_href_attribute(get_unsecured)
                get_secured = xml_helper.get_href_attribute(get_secured)
                post_unsecured = xml_helper.get_href_attribute(post_unsecured)
                post_secured = xml_helper.get_href_attribute(post_secured)

                # Assert that both (secure/unsecure) uris are None or none of them
                # This is possible for operations that are not supported by the service
                if get_secured is not None and get_unsecured is not None:
                    self.assertIsNotNone(get_secured, msg="The secured uri of '{}' is None!".format(operation))

                    # Assert that the secured version is different from the unsecured one
                    self.assertNotEqual(get_unsecured, get_secured, msg="The uri of '{}' has not been secured!".format(operation))

                    # Assert that the HOST_NAME constant appears in the secured uri
                    self.assertTrue(HOST_NAME in get_secured)

                if post_secured is not None and post_unsecured is not None:
                    self.assertIsNotNone(post_secured, msg="The secured uri of '{}' is None!".format(operation))
                    self.assertNotEqual(post_unsecured, post_secured, msg="The uri of '{}' has not been secured!".format(operation))
                    self.assertTrue(HOST_NAME in post_secured)
            else:
                pass