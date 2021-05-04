import logging

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase, Client
from django.urls import reverse

from MrMap.messages import SECURITY_PROXY_NOT_ALLOWED
from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE
from service import tasks
from service.helper import xml_helper
from service.helper import service_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum, OGCOperationEnum, DocumentEnum
from service.models import Document, Service
from service.settings import SERVICE_OPERATION_URI_TEMPLATE, ALLOWED_SRS
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD

# Prevent uninteresting logging of request connection pool
from tests.test_data import get_capabilitites_url
from users.models import Subscription

logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


class NewUpdateServiceViewTestCase(TestCase):
    def setUp(self):
        return
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)

        self.wms_metadatas = create_wms_service(group=self.user.groups.first(), how_much_services=1)

    def test_get_update_service_view(self):
        return
        response = self.client.get(
            reverse('resource:new-pending-update', args=(self.wms_metadatas[0].id,))+"?current-view=home",
        )
        self.assertEqual(response.status_code, 200)

    def test_post_valid_update_service_page1(self):
        return
        params = {
            'page': '1',
            'get_capabilities_uri': get_capabilitites_url().get('valid'),
        }
        response = self.client.post(
            reverse('resource:new-pending-update', args=(self.wms_metadatas[0].id,)),
            data=params
        )
        self.assertEqual(response.status_code, 303)
        try:
            Service.objects.get(is_update_candidate_for=self.wms_metadatas[0].service.id)
        except ObjectDoesNotExist:
            self.fail("No update candidate were found for the service.")

    def test_post_invalid_no_service_update_service_page1(self):
        return
        params = {
            'page': '1',
            'get_capabilities_uri': get_capabilitites_url().get('invalid_no_service'),
        }

        response = self.client.post(
            reverse('resource:new-pending-update', args=(self.wms_metadatas[0].id,))+"?current-view=home",
            data=params
        )

        self.assertEqual(response.status_code, 422)  # 'The given uri is not valid cause there is no service parameter.'

    def test_post_invalid_service_type_update_service_page1(self):
        return
        params = {
            'page': '1',
            'get_capabilities_uri': get_capabilitites_url().get('valid_wfs_version_202'),
        }

        response = self.client.post(
            reverse('resource:new-pending-update', args=(self.wms_metadatas[0].id,))+"?current-view=home",
            data=params
        )

        self.assertEqual(response.status_code, 422)

    def test_post_invalid_update_candidate_exists_update_service_page1(self):
        return
        params = {
            'page': '1',
            'get_capabilities_uri': get_capabilitites_url().get('valid'),
        }
        create_wms_service(is_update_candidate_for=self.wms_metadatas[0].service, group=self.user.groups.all()[0], user=self.user)

        response = self.client.post(
            reverse('resource:new-pending-update', args=(self.wms_metadatas[0].id,))+"?current-view=home",
            data=params
        )
        self.assertEqual(response.status_code, 422)  # "There are still pending update requests from user '{}' for this service.".format(self.user)


class ServiceTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        return
        """ Initial creation of objects that are needed during the tests

        Returns:

        """
        cls.user = create_superadminuser()

        cls.group = cls.user.groups.first()

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

        ## Creating a new service model instance for wms
        service = service_helper.create_service(
            cls.test_wms["type"],
            cls.test_wms["version"],
            cls.test_wms["uri"],
            cls.user,
            cls.group
        )
        cls.service_wms = service

        ## Creating a new service model instance for wfs
        service = service_helper.create_service(
            cls.test_wfs["type"],
            cls.test_wfs["version"],
            cls.test_wfs["uri"],
            cls.user,
            cls.group
        )
        cls.service_wfs = service

        cls.cap_doc_wms = Document.objects.get(
            metadata=cls.service_wms.metadata,
            document_type=DocumentEnum.CAPABILITY.value,
        )
        cls.cap_doc_wfs = Document.objects.get(
            metadata=cls.service_wfs.metadata,
            document_type=DocumentEnum.CAPABILITY.value,
        )

    def _get_logged_in_client(self):
        return
        """ Helping function to encapsulate the login process

        Returns:
             client (Client): The client object, which holds an active session for the user
             user_id (int): The user (id) who shall be logged in
        """
        if self.client is None:
            self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        return self.client

    def _get_logged_out_client(self):
        return
        """ Helping function to encapsulate the logout process

        Returns:
             client (Client): The client object, which holds an active session for the user
        """
        self.client.logout()
        return self.client

    def _get_num_of_layers(self, xml_obj):
        return
        """ Helping function to get the number of the layers in the service

        Args:
            xml_obj: The capabilities xml object
        Returns:
            The number of layer objects inside the xml object
        """
        layer_elems = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("Layer"), xml_obj) or []
        return len(layer_elems)

    def test_new_service_check_layer_num(self):
        return
        """ Tests whether all layer objects from the xml have been stored inside the service object

        Returns:

        """
        service = self.service_wms
        layers = service.get_subelements()
        cap_xml = xml_helper.parse_xml(self.cap_doc_wms.content)

        num_layers_xml = self._get_num_of_layers(cap_xml)
        num_layers_service = len(layers)

        self.assertEqual(num_layers_service, num_layers_xml)

    def test_new_service_check_metadata_not_null(self):
        return
        """ Tests whether the metadata for the new service and it's layers was created

        Returns:

        """
        service = self.service_wms
        layers = service.get_subelements()

        self.assertIsNotNone(service.metadata, msg="Service metadata does not exist!")
        for layer in layers:
            self.assertIsNotNone(layer.metadata, msg="Layer '{}' metadata does not exist!".format(layer.identifier))

    def test_new_service_check_capabilities_uri(self):
        return
        """ Tests whether capabilities uris for the service and layers are set.

        Performs a retrieve check: Connects to the given uri and checks if the received xml matches with the persisted
        capabilities document.
        Checks for the service.
        Checks for each layer.

        Returns:

        """
        service = self.service_wms
        layers = service.get_subelements()

        cap_doc = self.cap_doc_wms.content
        cap_uri = service.metadata.capabilities_original_uri
        connector = CommonConnector(url=cap_uri)
        connector.load()

        # Only check if the uri is valid and can be used to receive some data
        self.assertEqual(connector.status_code, 200, msg="URL '{}' didn't respond with status code 200".format(cap_uri))
        for layer in layers:
            cap_uri_layer = layer.metadata.capabilities_original_uri
            if cap_uri == cap_uri_layer:
                # we assume that the same uri in a layer will receive the same xml document. ONLY if the uri would be different
                # we run another check. We can be sure that this check will fail, since a capabilities document
                # should only be available using a unique uri - but you never know...
                continue
            connector = CommonConnector(url=cap_uri)
            self.assertEqual(
                connector.status_code, 200,
                msg="URL '{}' didn't respond with status code 200".format(cap_uri)
            )

    def test_new_service_check_describing_attributes(self):
        return
        """ Tests whether the describing attributes, such as title or abstract, are correct.

        Checks for the service.
        Checks for each layer.

        Returns:

        """
        service = self.service_wms
        layers = service.get_subelements()
        cap_xml = xml_helper.parse_xml(self.cap_doc_wms.content)

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

    def test_new_service_check_status(self):
        return
        """ Tests whether the registered service and its layers are deactivated by default.

        Checks for the service.
        Checks for each layer.

        Returns:

        """
        service = self.service_wms
        layers = service.get_subelements().select_related('metadata')

        self.assertFalse(service.is_active)
        for layer in layers:
            self.assertFalse(layer.metadata.is_active)

    def test_new_service_check_register_dependencies(self):
        return
        """ Tests whether the registered_by and register_for attributes are correctly set.

        Checks for the service.
        Checks for each layer.

        Returns:

        """
        service = self.service_wms
        layers = service.get_subelements()

        self.assertEqual(service.created_by, self.group)
        for layer in layers:
            self.assertEqual(layer.created_by, self.group)

    def test_new_service_check_version_and_type(self):
        return
        """ Tests whether the service has the correct version number and service type set.

        Checks for the service.
        Checks for each layer.

        Returns:

        """
        service = self.service_wms
        layers = service.get_subelements()

        self.assertEqual(service.service_type.name, self.test_wms.get("type").value)
        self.assertEqual(service.service_type.version, self.test_wms.get("version").value)
        for layer in layers:
            self.assertEqual(layer.service_type.name, self.test_wms.get("type").value)
            self.assertEqual(layer.service_type.version, self.test_wms.get("version").value)

    def test_new_service_check_reference_systems(self):
        return
        """ Tests whether the layers have all their reference systems, which are provided by the capabilities document.

        Checks for each layer.

        Returns:

        """
        layers = self.service_wms.get_subelements().select_related('metadata').prefetch_related('metadata__reference_system')
        cap_xml = self.cap_doc_wms.content

        for layer in layers:
            xml_layer_obj = xml_helper.try_get_single_element_from_xml("//Name[text()='{}']/parent::Layer".format(layer.identifier), cap_xml)
            if xml_layer_obj is None:
                # it is possible, that there are layers without a real identifier -> this is generally bad.
                # we have to ignore these and concentrate on those, which are identifiable
                continue
            xml_ref_systems = xml_helper.try_get_element_from_xml("./" + GENERIC_NAMESPACE_TEMPLATE.format("SRS"), xml_layer_obj)
            xml_ref_systems_strings = []
            for xml_ref_system in xml_ref_systems:
                xml_ref_systems_strings.append(xml_helper.try_get_text_from_xml_element(xml_ref_system))

            layer_ref_systems = layer.metadata.reference_system.all()
            for ref_system in layer_ref_systems:
                self.assertTrue(ref_system.code in ALLOWED_SRS, msg="Unallowed reference system registered: {}".format(ref_system.code))
                self.assertTrue(ref_system.code in xml_ref_systems_strings, msg="Reference system registered, which was not in the service: {}".format(ref_system.code))

    def test_secure_service(self):
        return
        """ Tests the securing functionalities

        1) Secure a service
        2) Try to perform an operation -> must fail
        3) Give performing user the permission (example call for WMS: GetMap, for WFS: GetFeature)
        4) Try to perform an operation -> must not fail

        Returns:

        """
        # activate service
        # since activating runs async as well, we need to call this function directly
        tasks.async_activate_service(self.service_wms.metadata.id, self.user.id, not self.service_wms.metadata.is_active)
        self.service_wms.refresh_from_db()

        service = self.service_wms
        metadata = service.metadata

        if metadata.is_service_type(OGCServiceEnum.WMS):
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
            client = self._get_logged_in_client()
            response = self._run_request(params, uri, "get", client)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.content.decode("utf-8"), SECURITY_PROXY_NOT_ALLOWED)

    def _run_request(self, params: dict, uri: str, request_type: str, client: Client = Client()):
        return
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

    def test_subscriptions(self):
        return
        """ Tests the functionality of subscribing a metadata record

        Returns:

        """
        md = self.service_wms.metadata

        uri = reverse("resource:subscription-new", args=(md.id,))

        # Case 0: User not logged in -> redirect to /home
        response = self._run_request({}, uri, "get")
        self.assertEqual(response.status_code, 302, msg="Anonymous user request has not been redirected to /home!")
        subscription_num = Subscription.objects.filter(
            metadata=md
        ).count()
        self.assertEqual(subscription_num, 0)

        # Case 1: user logged in -> redirect to subscription index
        client = self._get_logged_in_client()
        response = self._run_request({}, uri, "get", client)
        self.assertEqual(response.status_code, 302, msg="Logged in user has not been redirected to subscriptions index")
        subs_filtered = Subscription.objects.filter(
            metadata=md
        )
        subscription_num = subs_filtered.count()
        subscription = subs_filtered.first()
        self.assertEqual(subscription_num, 1)
        self.assertIsNotNone(subscription)
        self.assertEqual(subscription.user.id, self.user.id)
