import os

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from django.test import TestCase, Client
from django.utils import timezone

from service import tasks
from service.helper import service_helper, xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum
from service.models import Service, Layer, Document
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

        service_helper.persist_service_model_instance(self.service)
        self.service.persist_capabilities_doc(self.raw_data.service_capabilities_xml)


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
        #self.assertEqual(service.published_for, self.org)
        for layer in layers:
            self.assertEqual(layer.created_by, self.group)
            #self.assertEqual(layer.published_for, self.org)

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
        ]
        for check_func in checks:
            check_func(self.service, child_layers, cap_xml)

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

        ## case 0.0: Service is deactivated -> Original capabilities uri not reachable
        uri = "/service/capabilities/{}/original".format(self.service.metadata.id)
        response = self._run_request({}, uri, 'get')
        self.assertEqual(response.status_code, 423)  # 423 means the resource is currently locked (https://tools.ietf.org/html/rfc4918#section-11.3)

        ## case 0.1: Service is deactivated -> Current capabilities uri not reachable
        uri = "/service/capabilities/{}".format(self.service.metadata.id)
        response = self._run_request({}, uri, 'get')
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

        ## case 1.0: Service is activated -> Original capabilities uri is reachable
        uri = "/service/capabilities/{}/original".format(self.service.metadata.id)
        response = self._run_request({}, uri, 'get')
        self.assertEqual(response.status_code, 200)

        ## case 1.1: Service is deactivated -> Current capabilities uri not reachable
        uri = "/service/capabilities/{}".format(self.service.metadata.id)
        response = self._run_request({}, uri, 'get')
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






