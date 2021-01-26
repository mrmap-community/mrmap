import base64
from time import sleep, time

from django.test import TestCase, Client

from MrMap.settings import HOST_NAME, GENERIC_NAMESPACE_TEMPLATE
from editor.tasks import async_process_securing_access
from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum, OGCOperationEnum, DocumentEnum
from service.helper import service_helper, xml_helper
from service.models import Document, ProxyLog, Layer, AllowedOperation
from service.tasks import async_log_response, async_secure_service_task
from structure.models import Permission
from structure.permissionEnums import PermissionEnum
from tests.baker_recipes.db_setup import create_superadminuser
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD


OPERATION_BASE_URI_TEMPLATE = "/resource/metadata/{}/operation"
EDIT_BASE_URI_TEMPLATE = "/editor/metadata/{}?current-view=resource:index"
RESTORE_BASE_URI_TEMPLATE = "/editor/restore/{}?current-view=resource:index"

EDIT_ACCESS_BASE_URI_TEMPLATE = "/editor/access/{}?current-view=resource:index"


class EditorTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        """ Initial creation of objects that are needed during the tests

        Returns:

        """

        # create superuser
        cls.user = create_superadminuser()

        cls.group = cls.user.get_groups().first()

        cls.perms = cls.group.role.permissions

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
        service.activate_service(True)
        cls.service_wms = service

        ## Creating a new wfs service model instance
        service = service_helper.create_service(
            cls.test_wfs["type"],
            cls.test_wfs["version"],
            cls.test_wfs["uri"],
            cls.user,
            cls.group
        )
        service.activate_service(True)
        cls.service_wfs = service

        cls.cap_doc_wms = Document.objects.get(
            metadata=cls.service_wms.metadata,
            document_type=DocumentEnum.CAPABILITY.value,
            is_original=True
        )
        cls.cap_doc_wfs = Document.objects.get(
            metadata=cls.service_wfs.metadata,
            document_type=DocumentEnum.CAPABILITY.value,
            is_original=True
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
            "language_code": "ger",
            "licence": "",
        }

        ## case 0: User not logged in -> tries to edit -> fails
        client = Client()
        self._run_request(params, EDIT_BASE_URI_TEMPLATE.format(self.service_wms.metadata.id), "post", client)
        self.service_wms.refresh_from_db()
        self.assertNotEqual(self.service_wms.metadata.title, test_title, msg="Metadata title could be edited by not logged in user!")
        self.assertNotEqual(self.service_wms.metadata.abstract, test_abstract, msg="Metadata abstract could be edited by not logged in user!")
        self.assertNotEqual(self.service_wms.metadata.access_constraints, test_access_constraints, msg="Metadata access constraints could be edited by not logged in user!")

        ## case 1.1: User logged in, has no permission -> tries to edit -> fails
        client = self._get_logged_in_client()

        # manipulate user permissions
        edit_md_perm = Permission.objects.get_or_create(name=PermissionEnum.CAN_EDIT_METADATA.value)[0]
        self.perms.remove(edit_md_perm)

        self._run_request(params, EDIT_BASE_URI_TEMPLATE.format(self.service_wms.metadata.id), "post", client)
        self.service_wms.refresh_from_db()
        self.assertNotEqual(self.service_wms.metadata.title, test_title, msg="Metadata title could be edited by user without permission!")
        self.assertNotEqual(self.service_wms.metadata.abstract, test_abstract, msg="Metadata abstract could be edited by user without permission!")
        self.assertNotEqual(self.service_wms.metadata.access_constraints, test_access_constraints, msg="Metadata access constraints could be edited by user without permission!")

        # restore user permissions
        self.perms.add(edit_md_perm)

        ## case 1.2: User logged in -> tries to edit -> success
        client = self._get_logged_in_client()
        self._run_request(params, EDIT_BASE_URI_TEMPLATE.format(self.service_wms.metadata.id), "post", client)
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
        url = RESTORE_BASE_URI_TEMPLATE.format(self.service_wms.metadata.id)
        self._run_request({}, url, "get", client)
        self.assertEqual(self.service_wms.metadata.title, new_val, msg="Metadata was restored by not logged in user!")
        self.assertEqual(self.service_wms.metadata.abstract, new_val, msg="Metadata was restored by not logged in user!")
        self.assertEqual(self.service_wms.metadata.keywords.count(), 0, msg="Metadata was restored by not logged in user!")

        ## case 1.1: User logged in, has no permissions -> tries to restore -> fails
        client = self._get_logged_in_client()

        # manipulate user permissions
        edit_md_perm = Permission.objects.get_or_create(name=PermissionEnum.CAN_EDIT_METADATA.value)[0]
        self.perms.remove(edit_md_perm)

        url = RESTORE_BASE_URI_TEMPLATE.format(self.service_wms.metadata.id)

        self._run_request({"is_confirmed": "on"}, url, "post", client)
        self.assertEqual(self.service_wms.metadata.title, new_val, msg="Metadata was restored by a user without permission!")
        self.assertEqual(self.service_wms.metadata.abstract, new_val, msg="Metadata was restored by a user without permission!")
        self.assertEqual(self.service_wms.metadata.keywords.count(), 0, msg="Metadata was restored by a user without permission!")

        # restore permissions
        self.perms.add(edit_md_perm)

        ## case 1.2: User logged in -> tries to restore -> success
        self._run_request({"is_confirmed": "on"}, url, "post", client)
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
        async_process_securing_access(
            metadata.id,
            use_proxy=True,
            log_proxy=True,
            restrict_access=False,
        )

        self.cap_doc_wms.refresh_from_db()
        doc_unsecured = self.cap_doc_wms.content
        doc_secured = Document.objects.get(
            metadata=metadata,
            document_type=DocumentEnum.CAPABILITY.value,
            is_original=False,
        ).content

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

    def test_proxy_logging(self):
        """ Tests whether the proxy logger logs correctly.

        Returns:
        """
        # Prefetch for WMS
        proxy_logs_wms = ProxyLog.objects.filter(metadata=self.service_wms.metadata)
        pre_proxy_logs_wms_num = proxy_logs_wms.count()

        # Prefetch for WFS
        proxy_logs_wfs = ProxyLog.objects.filter(metadata=self.service_wfs.metadata)
        pre_proxy_logs_wfs_num = proxy_logs_wfs.count()

        # To avoid running celery in a separate test instance, we do not call the route. Instead we call the logic, which
        # is used to process access settings directly.
        async_process_securing_access(
            self.service_wms.metadata.id,
            use_proxy=True,
            log_proxy=True,
            restrict_access=False,
        )
        async_process_securing_access(
            self.service_wfs.metadata.id,
            use_proxy=True,
            log_proxy=True,
            restrict_access=False,
        )

        self.service_wms.metadata.refresh_from_db()
        self.service_wms.refresh_from_db()

        self.service_wfs.metadata.refresh_from_db()
        self.service_wfs.refresh_from_db()

        self.assertTrue(self.service_wms.metadata.log_proxy_access, msg="Test metadata logging access is not set for WMS!")
        self.assertTrue(self.service_wfs.metadata.log_proxy_access, msg="Test metadata logging access is not set for WFS!")

        # Run regular /operation request for WMS
        root_layer = Layer.objects.get(
            parent_service=self.service_wms,
            parent_layer=None
        )
        client = self._get_logged_in_client()
        url = OPERATION_BASE_URI_TEMPLATE.format(self.service_wms.metadata.id)
        param_width = 100
        param_height = 100
        params = {
            "request": "GetMap",
            "service": "WMS",
            "bbox": "7.518260643092100182,50.31584133059208597,7.644704820723687178,50.38426523684209002",
            "srs": "EPSG:4326",
            "version": OGCServiceVersionEnum.V_1_1_1.value,
            "width": str(param_width),
            "height": str(param_height),
            "layers": root_layer.identifier,
            "format": "image/png",
        }
        response = self._run_request(params, url, "get", client)
        self.assertEqual(response.status_code, 200, msg="Request returned status code {}".format(response.status_code))

        # Postfetch for WMS
        proxy_logs_wms = ProxyLog.objects.filter(metadata=self.service_wms.metadata)
        post_proxy_logs_wms_num = proxy_logs_wms.count()
        proxy_log_wms = proxy_logs_wms.first()
        async_log_response(
            proxy_log_wms.id,
            base64.b64encode(response.content).decode("UTF-8"),
            "GetMap",
            None
        )
        proxy_log_wms.refresh_from_db()

        # Run regular /operation request for WFS
        feature = self.service_wfs.subelements[0]
        url = OPERATION_BASE_URI_TEMPLATE.format(self.service_wfs.metadata.id)
        params = {
            "request": "GetFeature",
            "service": "WFS",
            "bbox": "231368.05064287804998457,5410244.19714341126382351,515259.67860294174170122,5660069.34592645335942507,urn:ogc:def:crs:EPSG::25832",
            "srsname": "urn:ogc:def:crs:EPSG::25832",
            "version": OGCServiceVersionEnum.V_2_0_0.value,
            "typenames": feature.metadata.identifier,
            "typename": feature.metadata.identifier,
        }
        response = self._run_request(params, url, "get", client)
        self.assertEqual(response.status_code, 200, msg="Request returned status code {}".format(response.status_code))

        # Postfetch for WFS
        proxy_logs_wfs = ProxyLog.objects.filter(metadata=self.service_wfs.metadata)
        post_proxy_logs_wfs_num = proxy_logs_wfs.count()
        proxy_log_wfs = proxy_logs_wfs.first()
        async_log_response(
            proxy_log_wfs.id,
            base64.b64encode(b"".join(response.streaming_content)).decode("UTF-8"),
            "GetFeature",
            "gml3",
        )
        proxy_log_wfs.refresh_from_db()

        # Assertions for WMS Log
        self.assertNotEqual(pre_proxy_logs_wms_num, post_proxy_logs_wms_num, msg="No new proxy log record created!")
        self.assertEqual(pre_proxy_logs_wms_num + 1, post_proxy_logs_wms_num, msg="More than one log record was created!")
        self.assertEqual(proxy_log_wms.operation, "GetMap", msg="Wrong operation type logged! Was {} but {} expected!".format(proxy_log_wms.operation, "GetMap"))
        expected_logged_megapixel = round((param_height * param_height) / 1000000, 4)
        self.assertEqual(proxy_log_wms.response_wms_megapixel, expected_logged_megapixel, msg="Wrong megapixel count! Was {} but {} expected!".format(proxy_log_wms.response_wms_megapixel, expected_logged_megapixel))

        # Assertions for WFS Log
        self.assertNotEqual(pre_proxy_logs_wfs_num, post_proxy_logs_wfs_num, msg="No new proxy log record created!")
        self.assertEqual(pre_proxy_logs_wfs_num + 1, post_proxy_logs_wfs_num, msg="More than one log record was created!")
        self.assertEqual(proxy_log_wfs.operation, "GetFeature", msg="Wrong operation type logged! Was {} but {} expected!".format(proxy_log_wfs.operation, "GetFeature"))
        self.assertGreater(proxy_log_wfs.response_wfs_num_features, 0, msg="Wrong returned feature count! Was {}!".format(proxy_log_wfs.response_wfs_num_features))

    def test_access_securing(self):
        """ Tests whether the securing of a service changes the returned restuls on GetFeature and GetMap.

        Since we cannot qualify the content itself, we need to check the quantity inside the response.

        First, secure WMS directly.
        For WFS only activate proxy and proxy logging.

        Then run a regular GetMap request on the WMS. An unsecured response would log img_height * img_width pixels in a log.
        A secured response would log a smaller amount of pixels, since there will be parts cutted out!

        For WFS we first need to fetch the amount of features an unsecured request would return -> we simply log it using LogProxy.
        Afterwards we secure the WFS using a geometry and rerun the same request. We expect a lower amount of features in this request!

        Returns:

        """
        client = self._get_logged_in_client()

        # Secure WMS using geometry
        async_process_securing_access(
            self.service_wms.metadata.id,
            use_proxy=True,
            log_proxy=True,
            restrict_access=True,
        )
        async_secure_service_task(
            self.service_wms.metadata.id,
            self.group.id,
            ["GetMap", "GetFeatureInfo"],
            '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[7.223511,50.312919],[7.223511,50.461826],[7.616272,50.461826],[7.616272,50.312919],[7.223511,50.312919]]]}}]}',
        )

        # Assert existing securedoperations for service and all subelements
        wms_elements = [self.service_wms.metadata] + [elem.metadata for elem in self.service_wms.subelements]
        secured_operations_wms = AllowedOperation.objects.filter(
            secured_metadata__in=wms_elements
        )

        wms_operations = ["GetMap", "GetFeatureInfo"]
        for op in secured_operations_wms:
            self.assertTrue(op.operation in wms_operations, msg="Wrong operation stored in secured operation! Found {}!".format(op.operation))
            self.assertEqual(op.allowed_group, self.group, msg="Wrong group got access! Expected {} but got {}!".format(self.group, op.allowed_group))
            self.assertGreater(op.bounding_geometry.area, 0, msg="Invalid area size detected: {}".format(op.bounding_geometry.area))

        # Check request result!
        # Run regular /operation request for WMS
        root_layer = Layer.objects.get(
            parent_service=self.service_wms,
            parent_layer=None
        )
        url = OPERATION_BASE_URI_TEMPLATE.format(self.service_wms.metadata.id)
        param_width = 1000
        param_height = 1000
        params = {
            "request": "GetMap",
            "service": "WMS",
            "bbox": "7.393799,50.359379,7.68219,50.534343",
            "srs": "EPSG:4326",
            "version": OGCServiceVersionEnum.V_1_1_1.value,
            "width": str(param_width),
            "height": str(param_height),
            "layers": root_layer.identifier,
            "format": "image/png",
        }
        response = self._run_request(params, url, "get", client)
        proxy_log = ProxyLog.objects.get(
            metadata=self.service_wms.metadata
        )
        async_log_response(
            proxy_log.id,
            base64.b64encode(response.content).decode("UTF-8"),
            "GetMap",
            None
        )
        proxy_log.refresh_from_db()

        self.assertEqual(response.status_code, 200, msg="Wrong")

        full_logged_megapixel = round((param_height * param_height) / 1000000, 4)
        self.assertLessEqual(proxy_log.response_wms_megapixel, full_logged_megapixel, msg="Logged megapixel ({}) not smaller than full image megapixel ({}). Securing might not worked!".format(proxy_log.response_wms_megapixel, full_logged_megapixel))

        # WFS
        # Activate the logging for WFS
        async_process_securing_access(
            self.service_wfs.metadata.id,
            use_proxy=True,
            log_proxy=True,
            restrict_access=False,
        )
        # First run an unsecured request, to get the amount of unsecured features that are returned!
        feature = self.service_wfs.subelements[0]
        url = OPERATION_BASE_URI_TEMPLATE.format(self.service_wfs.metadata.id)
        params = {
            "request": "GetFeature",
            "service": "WFS",
            "bbox": "231368.05064287804998457,5410244.19714341126382351,515259.67860294174170122,5660069.34592645335942507,urn:ogc:def:crs:EPSG::25832",
            "srsname": "urn:ogc:def:crs:EPSG::25832",
            "version": OGCServiceVersionEnum.V_2_0_0.value,
            "typenames": feature.metadata.identifier,
            "typename": feature.metadata.identifier,
        }
        response = self._run_request(params, url, "get", client)
        self.assertEqual(response.status_code, 200, msg="Wrong status code returned: {}".format(response.status_code))
        proxy_log = ProxyLog.objects.filter(
            metadata=self.service_wfs.metadata
        ).first()
        async_log_response(
            proxy_log.id,
            base64.b64encode(b"".join(response.streaming_content)).decode("UTF-8"),
            "GetFeature",
            "gml3",
        )
        proxy_log.refresh_from_db()
        pre_num_logged_features = proxy_log.response_wfs_num_features

        # Secure WFS using geometry
        async_process_securing_access(
            self.service_wfs.metadata.id,
            use_proxy=True,
            log_proxy=True,
            restrict_access=True,
        )
        async_secure_service_task(
            self.service_wfs.metadata.id,
            self.group.id,
            ["GetFeature"],
            '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[7.223511,50.312919],[7.223511,50.461826],[7.616272,50.461826],[7.616272,50.312919],[7.223511,50.312919]]]}}]}',
        )

        wfs_elements = [self.service_wfs.metadata] + [elem.metadata for elem in self.service_wfs.subelements]
        secured_operations_wfs = AllowedOperation.objects.filter(
            secured_metadata__in=wfs_elements
        )
        for op in secured_operations_wfs:
            self.assertEqual(op.operation, "GetFeature", msg="Wrong operation stored in secured operation!")
            self.assertEqual(op.allowed_group, self.group, msg="Wrong group got access! Expected {} but got {}!".format(self.group, op.allowed_group))
            self.assertGreater(op.bounding_geometry.area, 0, msg="Invalid area size detected: {}".format(op.bounding_geometry.area))

        # Rerun request
        response = self._run_request(params, url, "get", client)
        self.assertEqual(response.status_code, 200, msg="Wrong status code returned: {}".format(response.status_code))

        # Get the new logged record for the WFS
        proxy_log = ProxyLog.objects.filter(
            metadata=self.service_wfs.metadata
        ).first()
        async_log_response(
            proxy_log.id,
            base64.b64encode(response.content).decode("UTF-8"),
            "GetFeature",
            "gml3",
        )
        proxy_log.refresh_from_db()
        post_num_logged_features = proxy_log.response_wfs_num_features

        self.assertLessEqual(post_num_logged_features, pre_num_logged_features, msg="Logged number of features ({}) not smaller than unsecured number of features ({}). Securing might not worked!".format(post_num_logged_features, pre_num_logged_features))

