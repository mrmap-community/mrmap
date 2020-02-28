import os

from copy import copy
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from django.test import TestCase, Client
from django.utils import timezone

from MapSkinner.messages import SECURITY_PROXY_NOT_ALLOWED
from MapSkinner.settings import GENERIC_NAMESPACE_TEMPLATE, HOST_NAME, HTTP_OR_SSL
from service import tasks
from service.helper import service_helper, xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum, OGCOperationEnum
from service.models import Service, Layer, Document, Metadata
from service.settings import SERVICE_OPERATION_URI_TEMPLATE
from structure.models import User, Group, Role, Permission


class ServiceTestCase(TestCase):
    """ PLEASE NOTE:

    To run these tests, you have to run the celery worker background process!

    """

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

        self.test_wfs = {
            "title": "Nutzung",
            "version": OGCServiceVersionEnum.V_1_0_0,
            "type": OGCServiceEnum.WFS,
            "uri": "https://www.geoportal.rlp.de/mapbender/php/mod_showMetadata.php/../wfs.php?FEATURETYPE_ID=2672&PHPSESSID=7qiruaoul2pdcadcohs7doeu07",
        }


        # Since the registration of a service is performed async in an own process, the testing is pretty hard.
        # Therefore in here we won't perform the regular route testing, but rather run unit tests and check whether the
        # important components work as expected.
        # THIS MEANS WE CAN NOT CHECK PERMISSIONS IN HERE; SINCE WE TESTS ON THE LOWER LEVEL OF THE PROCESS

        ## Creating a new service model instance
        service = service_helper.get_service_model_instance(
            self.test_wms["type"],
            self.test_wms["version"],
            self.test_wms["uri"],
            self.user,
            self.group
        )
        self.raw_data = service.get("raw_data", None)
        self.service = service.get("service", None)

        # run process without an external authentication - since the service does not require an authentication
        service_helper.persist_service_model_instance(self.service, external_auth=None)
        self.service.persist_capabilities_doc(self.raw_data.service_capabilities_xml)

    def _get_logged_in_client(self, user: User):
        """ Helping function to encapsulate the login process

        Returns:
             client (Client): The client object, which holds an active session for the user
             user_id (int): The user (id) who shall be logged in
        """
        client = Client()
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        response = client.post("/", data={"username": user.username, "password": self.pw})
        user.refresh_from_db()
        self.assertEqual(response.url, "{}{}/home".format(HTTP_OR_SSL, HOST_NAME), msg="Redirect wrong")
        self.assertEqual(user.logged_in, True, msg="User not logged in")
        return client

    def _get_num_of_layers(self, xml_obj):
        """ Helping function to get the number of the layers in the service

        Args:
            xml_obj: The capabilities xml object
        Returns:
            The number of layer objects inside the xml object
        """
        layer_elems = xml_helper.try_get_element_from_xml("//Layer", xml_obj)
        return len(layer_elems)

    def _test_new_service_check_layer_num(self, service: Service, layers: QuerySet, cap_xml):
        """ Tests whether all layer objects from the xml have been stored inside the service object

        Args:
            service (Service): The service object
            layers (QuerySet): The querySet object, containing all child layers of this service
            cap_xml: The capabilities document xml object
        Returns:

        """
        num_layers_xml = self._get_num_of_layers(cap_xml)
        num_layers_service = layers.count()

        self.assertEqual(num_layers_service, num_layers_xml)

    def _test_new_service_check_metadata_not_null(self, service: Service, layers: QuerySet, cap_xml):
        """ Tests whether the metadata for the new service and it's layers was created

        Args:
            service (Service): The service object
            layers (QuerySet): The querySet object, containing all child layers of this service
            cap_xml: The capabilities document xml object
        Returns:

        """
        self.assertIsNotNone(service.metadata, msg="Service metadata does not exist!")
        for layer in layers:
            self.assertIsNotNone(layer.metadata, msg="Layer '{}' metadata does not exist!".format(layer.identifier))

    def _test_new_service_check_capabilities_uri(self, service: Service, layers: QuerySet, cap_xml):
        """ Tests whether capabilities uris for the service and layers are set.

        Performs a retrieve check: Connects to the given uri and checks if the received xml matches with the persisted
        capabilities document.
        Checks for the service.
        Checks for each layer.

        Args:
            service (Service): The service object
            layers (QuerySet): The querySet object, containing all child layers of this service
            cap_xml: The capabilities document xml object
        Returns:

        """
        cap_doc = Document.objects.get(
            related_metadata=service.metadata
        ).original_capability_document
        cap_uri = service.metadata.capabilities_original_uri
        connector = CommonConnector(url=cap_uri)
        connector.load()
        received_xml = connector.content
        if isinstance(received_xml, bytes):
            received_xml = received_xml.decode("UTF-8")

        self.assertEqual(received_xml, cap_doc, msg="Received capabilities document does not match the persisted one!")
        for layer in layers:
            cap_uri_layer = layer.metadata.capabilities_original_uri
            if cap_uri == cap_uri_layer:
                # we assume that the same uri in a layer will receive the same xml document. ONLY if the uri would be different
                # we run another check. We can be sure that this check will fail, since a capabilities document
                # should only be available using a unique uri - but you never know...
                continue
            connector = CommonConnector(url=cap_uri)
            connector.load()
            received_xml = connector.content
            self.assertEqual(received_xml, cap_doc,
                             msg="Received capabilities document for layer '{}' does not match the persisted one"
                             .format(layer.identifier)
                             )

    def _test_new_service_check_describing_attributes(self, service: Service, layers: QuerySet, cap_xml):
        """ Tests whether the describing attributes, such as title or abstract, are correct.

        Checks for the service.
        Checks for each layer.

        Args:
            service (Service): The service object
            layers (QuerySet): The querySet object, containing all child layers of this service
            cap_xml: The capabilities document xml object
        Returns:

        """
        xml_title = xml_helper.try_get_text_from_xml_element(cap_xml, "//Service/Title")
        xml_abstract = xml_helper.try_get_text_from_xml_element(cap_xml, "//Service/Abstract")

        self.assertEqual(service.metadata.title, xml_title)
        self.assertEqual(service.metadata.abstract, xml_abstract)

        # run for layers
        for layer in layers:
            xml_layer = xml_helper.try_get_single_element_from_xml("//Name[text()='{}']/parent::Layer".format(layer.identifier), cap_xml)
            if xml_layer is None:
                # this might happen for layers which do not provide a unique identifier. We generate an identifier automatically in this case.
                # this generated identifier - of course - can not be found in the xml document.
                continue
            xml_title = xml_helper.try_get_text_from_xml_element(xml_layer, "./Title")
            xml_abstract = xml_helper.try_get_text_from_xml_element(xml_layer, "./Abstract")
            self.assertEqual(layer.metadata.title, xml_title, msg="Failed for layer with identifier '{}' and title '{}'".format(layer.identifier, layer.metadata.title))
            self.assertEqual(layer.metadata.abstract, xml_abstract, msg="Failed for layer with identifier '{}' and title '{}'".format(layer.identifier, layer.metadata.title))

    def _test_new_service_check_status(self, service: Service, layers: QuerySet, cap_xml):
        """ Tests whether the registered service and its layers are deactivated by default.

        Checks for the service.
        Checks for each layer.

        Args:
            service (Service): The service object
            layers (QuerySet): The querySet object, containing all child layers of this service
            cap_xml: The capabilities document xml object
        Returns:

        """
        self.assertFalse(service.is_active)
        for layer in layers:
            self.assertFalse(layer.is_active)

    def _test_new_service_check_register_dependencies(self, service: Service, layers: QuerySet, cap_xml):
        """ Tests whether the registered_by and register_for attributes are correctly set.

        Checks for the service.
        Checks for each layer.

        Args:
            service (Service): The service object
            layers (QuerySet): The querySet object, containing all child layers of this service
            cap_xml: The capabilities document xml object
        Returns:

        """
        self.assertEqual(service.created_by, self.group)
        for layer in layers:
            self.assertEqual(layer.created_by, self.group)

    def _test_new_service_check_version_and_type(self, service: Service, layers: QuerySet, cap_xml):
        """ Tests whether the service has the correct version number and service type set.

        Checks for the service.
        Checks for each layer.

        Args:
            service (Service): The service object
            layers (QuerySet): The querySet object, containing all child layers of this service
            cap_xml: The capabilities document xml object
        Returns:

        """
        self.assertEqual(service.servicetype.name, self.test_wms.get("type").value)
        self.assertEqual(service.servicetype.version, self.test_wms.get("version").value)
        for layer in layers:
            self.assertEqual(layer.servicetype.name, self.test_wms.get("type").value)
            self.assertEqual(layer.servicetype.version, self.test_wms.get("version").value)

    def _test_new_service_check_reference_systems(self, service: Service, layers: QuerySet, cap_xml):
        """ Tests whether the layers have all their reference systems, which are provided by the capabilities document.

        Checks for each layer.

        Args:
            service (Service): The service object
            layers (QuerySet): The querySet object, containing all child layers of this service
            cap_xml: The capabilities document xml object
        Returns:

        """
        for layer in layers:
            xml_layer_obj = xml_helper.try_get_single_element_from_xml("//Name[text()='{}']/parent::Layer".format(layer.identifier), cap_xml)
            if xml_layer_obj is None:
                # it is possible, that there are layers without a real identifier -> this is generally bad.
                # we have to ignore these and concentrate on those, which are identifiable
                continue
            xml_ref_systems = xml_helper.try_get_element_from_xml("./SRS", xml_layer_obj)
            xml_ref_systems_strings = []
            for xml_ref_system in xml_ref_systems:
                xml_ref_systems_strings.append(xml_helper.try_get_text_from_xml_element(xml_ref_system))

            layer_ref_systems =layer.metadata.reference_system.all()
            self.assertEqual(len(xml_ref_systems), len(layer_ref_systems))
            for ref_system in layer_ref_systems:
                self.assertTrue("{}{}".format(ref_system.prefix, ref_system.code) in xml_ref_systems_strings)

    def test_new_service(self):
        """ Tests the service registration functionality

        Returns:

        """

        # since we have currently no chance to test using self-created test data, we need to work with the regular
        # capabilities documents and their information. Therefore we assume, that the low level xml reading functions
        # from xml_helper are (due to their low complexity) working correctly, and test if the information we can get
        # from there, match to the ones we get after the service creation.

        child_layers = Layer.objects.filter(
            parent_service=self.service
        )
        cap_xml = xml_helper.parse_xml(self.raw_data.service_capabilities_xml)
        checks = [
            self._test_new_service_check_layer_num,
            self._test_new_service_check_metadata_not_null,
            self._test_new_service_check_capabilities_uri,
            self._test_new_service_check_describing_attributes,
            self._test_new_service_check_status,
            self._test_new_service_check_register_dependencies,
            self._test_new_service_check_version_and_type,
            self._test_new_service_check_reference_systems,
            #self.test_proxy_service,
        ]
        for check_func in checks:
            check_func(self.service, child_layers, cap_xml)

    def _test_proxy_is_set(self, metadata: Metadata, doc_unsecured: str, doc_secured: str):
        """ Tests whether the proxy was set properly.

        Args:
            metadata (Metadata): The metadata object
            doc_unsecured (str): The unsecured document as string
            doc_secured (str): The secured document as string
        Returns:
        """
        # Check for all operations if the uris has been changed!
        # Do not check for GetCapabilities, since we always change this uri during registration!
        # Make sure all versions can be matched by the code - the xml structure differs a lot from version to version
        service_type = metadata.get_service_type()
        service_version = metadata.get_service_version()

        if service_type == OGCServiceEnum.WMS.value:
            operations = [
                OGCOperationEnum.GET_MAP.value,
                OGCOperationEnum.GET_FEATURE_INFO.value,
                OGCOperationEnum.DESCRIBE_LAYER.value,
                OGCOperationEnum.GET_LEGEND_GRAPHIC.value,
                OGCOperationEnum.GET_STYLES.value,
                OGCOperationEnum.PUT_STYLES.value,
            ]
        elif service_type == OGCServiceEnum.WFS.value:
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
                if service_type == OGCServiceEnum.WMS.value:
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

            elif service_version == OGCServiceVersionEnum.V_1_1_0 or service_version == OGCServiceVersionEnum.V_2_0_0 or service_version == OGCServiceVersionEnum.V_2_0_2:
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

    def test_proxy_service(self):
        """ Tests the securing functionality for services

        Returns:

        """
        metadata = self.service.metadata

        cap_doc_secured = Document.objects.get(
            related_metadata=metadata
        )

        # Create copy of 'cap_doc_secured' (which isn't secured yet) to avoid a simple reference between both variables
        cap_doc_unsecured = copy(cap_doc_secured)
        cap_doc_unsecured = cap_doc_unsecured.current_capability_document

        # Proxy the service!
        metadata.set_proxy(True)

        # Fetch the secured status for 'cap_doc_secured' from the db
        cap_doc_secured.refresh_from_db()
        cap_doc_secured = cap_doc_secured.current_capability_document

        # we expect that
        # 1) all uris of the capabilities document have been changed to use the internal proxy
        # 2) operations can not be performed by anyone who has no permission
        self._test_proxy_is_set(metadata, cap_doc_unsecured, cap_doc_secured)

    def test_secure_service(self):
        """ Tests the securing functionalities

        1) Secure a service
        2) Try to perform an operation -> must fail
        3) Give performing user the permission (example call for WMS: GetMap, for WFS: GetFeature)
        4) Try to perform an operation -> must not fail

        Args:
            service (Service):
            child_layers:
            cap_xml:
        Returns:

        """
        # activate service
        # since activating runs async as well, we need to call this function directly
        tasks.async_activate_service(self.service.id, self.user.id)
        self.service.refresh_from_db()

        service = self.service
        metadata = service.metadata
        service_type = metadata.get_service_type()


        if service_type == OGCServiceEnum.WMS.value:
            uri = SERVICE_OPERATION_URI_TEMPLATE.format(metadata.id)
            params = {
                "request": OGCOperationEnum.GET_MAP.value,
                "version": OGCServiceVersionEnum.V_1_1_1.value,
                "layers": "atkis1",  # the root layer for test data
                "bbox": "6.3635678506, 49.8043950464, 8.2910611844, 50.4544433675",
                "srs": "EPSG:4326",
                "format": "png",
                "width": "100",
                "height": "100",
            }

            # case 0: Service not secured -> Runs!
            response = self._run_request(params, uri, "get")
            self.assertEqual(response.status_code, 200)

            # Proxy the service!
            metadata.set_proxy(True)

            # Secure the service!
            metadata.set_secured(True)

            # case 1: Service secured but no permission was given to any user, guest user tries to perform request    -> Fails!
            response = self._run_request(params, uri, "get")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.content.decode("utf-8"), SECURITY_PROXY_NOT_ALLOWED)

            # case 2: Service secured but no permission was given to any user, logged in user performs request via logged in client     -> Fails!
            client = self._get_logged_in_client(self.user)
            response = self._run_request(params, uri, "get", client)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.content.decode("utf-8"), SECURITY_PROXY_NOT_ALLOWED)


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

    def test_activating_service(self):
        """ Tests if a service can be activated properly.

        Checks if access to resources will be restricted if deactivated.

        Returns:

        """

        # A deactivated service is not reachable from outside
        # This means we need to fire some requests and check if the documents and links of this service are available
        self.assertFalse(self.service.is_active)

        ## case 0.1: Service is deactivated -> Current capabilities uri not reachable
        uri = "/service/metadata/{}/operation?".format(self.service.metadata.id)
        response = self._run_request(
            {
                "request": "GetCapabilities",
            },
            uri,
            'get'
        )
        self.assertEqual(response.status_code, 423)  # 423 means the resource is currently locked

        ## case 0.2: Service is deactivated -> Current metadata uri not reachable
        uri = "/service/metadata/{}".format(self.service.metadata.id)
        response = self._run_request({}, uri, 'get')
        self.assertEqual(response.status_code, 423)  # 423 means the resource is currently locked

        # check for dataset metadata -> there should be no dataset metadata on a whole service
        uri = "/service/metadata/dataset/{}".format(self.service.metadata.id)
        response = self._run_request({}, uri, 'get')
        self.assertEqual(response.status_code, 423)  # 423 means the resource is currently locked

        # activate service
        # since activating runs async as well, we need to call this function directly
        tasks.async_activate_service(self.service.id, self.user.id)
        self.service.refresh_from_db()

        ## case 1.1: Service is deactivated -> Current capabilities uri not reachable
        uri = "/service/metadata/{}/operation?".format(self.service.metadata.id)
        response = self._run_request(
            {
                "request": "GetCapabilities"
            },
            uri,
            'get'
        )
        self.assertEqual(response.status_code, 200)

        ## case 1.2: Service is deactivated -> Current metadata uri not reachable
        uri = "/service/metadata/{}".format(self.service.metadata.id)
        response = self._run_request({}, uri, 'get')
        self.assertEqual(response.status_code, 200)

        # check for dataset metadata -> there should be no dataset metadata on a whole service
        uri = "/service/metadata/dataset/{}".format(self.service.metadata.id)
        response = self._run_request({}, uri, 'get')
        self.assertEqual(response.status_code, 404)

    def test_remove_service(self):
        """ Tests if a service can be removed with all its children

        Returns:

        """
        tasks.async_remove_service_task(self.service.id)
        child_objects = Service.objects.filter(
            parent_service=self.service
        )
        self.assertEqual(child_objects.count(), 0, msg="Not all child elements were removed!")
        exists = True
        try:
            self.service.refresh_from_db()
        except ObjectDoesNotExist:
            exists = False
        self.assertFalse(exists, msg="Service was not removed!")






