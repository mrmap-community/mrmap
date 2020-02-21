import urllib
import uuid

import os

from django.contrib.gis.geos import Polygon, GeometryCollection
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.contrib.gis.db import models
from django.utils import timezone

from MapSkinner.messages import PARAMETER_ERROR
from MapSkinner.settings import HTTP_OR_SSL, HOST_NAME, GENERIC_NAMESPACE_TEMPLATE, ROOT_URL, XML_NAMESPACES
from MapSkinner import utils
from service.helper.common_connector import CommonConnector
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum, MetadataEnum, OGCOperationEnum
from service.helper.crypto_handler import CryptoHandler
from service.settings import DEFAULT_SERVICE_BOUNDING_BOX, EXTERNAL_AUTHENTICATION_FILEPATH, \
    SERVICE_OPERATION_URI_TEMPLATE, SERVICE_LEGEND_URI_TEMPLATE, SERVICE_DATASET_URI_TEMPLATE
from structure.models import Group, Organization
from service.helper import xml_helper


class Resource(models.Model):
    uuid = models.CharField(max_length=255, default=uuid.uuid4())
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Group, on_delete=models.DO_NOTHING, null=True, blank=True)
    last_modified = models.DateTimeField(null=True)
    is_deleted = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    def save(self, update_last_modified=True, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if update_last_modified:
            # We always want to have automatically the last timestamp from the latest change!
            # ONLY if the function is especially called with a False flag in update_last_modified, we will not change the record's last change
            self.last_modified = timezone.now()
        super().save(force_insert, force_update, using, update_fields)

    class Meta:
        abstract = True


class Keyword(models.Model):
    keyword = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.keyword


class ProxyLog(models.Model):
    from structure.models import User
    metadata = models.ForeignKey('Metadata', on_delete=models.DO_NOTHING, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, null=True, blank=True)
    uri = models.CharField(max_length=1000, null=True, blank=True)
    post_body = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)


class RequestOperation(models.Model):
    operation_name = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.operation_name


class SecuredOperation(models.Model):
    operation = models.ForeignKey(RequestOperation, on_delete=models.CASCADE, null=True, blank=True)
    allowed_group = models.ForeignKey(Group, related_name="allowed_operations", on_delete=models.CASCADE, null=True, blank=True)
    bounding_geometry = models.GeometryCollectionField(blank=True, null=True)
    secured_metadata = models.ForeignKey('Metadata', related_name="secured_operations", on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return str(self.id)

    def delete(self, using=None, keep_parents=False):
        """ Overwrites builtin delete() method with model specific logic.

        If a SecuredOperation will be deleted, all related subelements of the secured_metadata have to be freed from
        existing SecuredOperation records as well.

        Args:
            using:
            keep_parents:
        Returns:

        """
        md = self.secured_metadata
        operation = self.operation
        group = self.allowed_group

        md_type = md.metadata_type.type

        # continue with possibly existing children
        if md_type == MetadataEnum.FEATURETYPE.value:
            sec_ops = SecuredOperation.objects.filter(
                secured_metadata=md,
                operation=operation,
                allowed_group=group
            )
            sec_ops.delete()

        elif md_type == MetadataEnum.SERVICE.value or md_type == MetadataEnum.LAYER.value:
            service_type = md.service.servicetype.name
            if service_type == OGCServiceEnum.WFS.value:
                # find all wfs featuretypes
                featuretypes = md.service.featuretypes.all()
                for featuretype in featuretypes:
                    sec_ops = SecuredOperation.objects.filter(
                        secured_metadata=featuretype.metadata,
                        operation=operation,
                        allowed_group=group,
                    )
                    sec_ops.delete()

            elif service_type == OGCServiceEnum.WMS.value:
                if md.service.is_root:
                    # find root layer
                    layer = Layer.objects.get(
                        parent_layer=None,
                        parent_service=md.service
                    )
                else:
                    # find layer which is described by this metadata
                    layer = Layer.objects.get(
                        metadata=md
                    )

                # remove root layer secured operation
                sec_op = SecuredOperation.objects.filter(
                    secured_metadata=layer.metadata,
                    operation=operation,
                    allowed_group=group
                )
                sec_op.delete()

                # remove secured operations of root layer children
                for child_layer in layer.child_layer.all():
                    sec_ops = SecuredOperation.objects.filter(
                        secured_metadata=child_layer.metadata,
                        operation=operation,
                        allowed_group=group,
                    )
                    sec_ops.delete()
                    child_layer.delete_children_secured_operations(child_layer, operation, group)

        # delete current object
        super().delete(using, keep_parents)


class MetadataOrigin(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class MetadataRelation(models.Model):
    metadata_from = models.ForeignKey('Metadata', on_delete=models.CASCADE, related_name="related_metadata_from")
    metadata_to = models.ForeignKey('Metadata', on_delete=models.CASCADE, related_name="related_metadata_to")
    relation_type = models.CharField(max_length=255, null=True, blank=True)
    internal = models.BooleanField(default=False)
    origin = models.ForeignKey(MetadataOrigin, on_delete=models.CASCADE)

    def __str__(self):
        return "{} {} {}".format(self.metadata_from.title, self.relation_type, self.metadata_to.title)


class ExternalAuthentication(models.Model):
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=500)
    auth_type = models.CharField(max_length=100)
    metadata = models.OneToOneField('Metadata', on_delete=models.DO_NOTHING, null=True, blank=True, related_name="external_authentication")

    def delete(self, using=None, keep_parents=False):
        """ Overwrites default delete function

        Removes local stored file if it exists!

        Args;
            using:
            keep_parents:
        Returns:
        """
        # remove local stored key
        filepath = "{}/md_{}.key".format(EXTERNAL_AUTHENTICATION_FILEPATH, self.metadata.id)
        try:
            os.remove(filepath)
        except FileNotFoundError:
            pass
        super().delete(using, keep_parents)

    def encrypt(self, key: str):
        """ Encrypts the login credentials using a given key

        Args:
            key (str):
        Returns:

        """
        crypto_handler = CryptoHandler(msg=self.username, key=key)
        crypto_handler.encrypt()
        self.username = crypto_handler.crypt_message.decode("ascii")

        crypto_handler.message = self.password
        crypto_handler.encrypt()
        self.password = crypto_handler.crypt_message.decode("ascii")

    def decrypt(self, key):
        """ Decrypts the login credentials using a given key

        Args:
            key:
        Returns:

        """
        crypto_handler = CryptoHandler()
        crypto_handler.key = key

        crypto_handler.crypt_message = self.password.encode("ascii")
        crypto_handler.decrypt()
        self.password = crypto_handler.message.decode("ascii")

        crypto_handler.crypt_message = self.username.encode("ascii")
        crypto_handler.decrypt()
        self.username = crypto_handler.message.decode("ascii")


class Metadata(Resource):
    identifier = models.CharField(max_length=255, null=True)
    title = models.CharField(max_length=255)
    abstract = models.TextField(null=True, blank=True)
    online_resource = models.CharField(max_length=500, null=True, blank=True)  # where the service data can be found

    capabilities_original_uri = models.CharField(max_length=500, blank=True, null=True)
    capabilities_uri = models.CharField(max_length=500, blank=True, null=True)

    service_metadata_original_uri = models.CharField(max_length=500, blank=True, null=True)
    service_metadata_uri = models.CharField(max_length=500, blank=True, null=True)

    contact = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, blank=True, null=True)
    terms_of_use = models.ForeignKey('TermsOfUse', on_delete=models.DO_NOTHING, null=True)
    access_constraints = models.TextField(null=True, blank=True)
    fees = models.TextField(null=True, blank=True)

    last_remote_change = models.DateTimeField(null=True, blank=True)  # the date time, when the metadata was changed where it comes from
    status = models.IntegerField(null=True)
    use_proxy_uri = models.BooleanField(default=False)
    log_proxy_access = models.BooleanField(default=False)
    spatial_res_type = models.CharField(max_length=100, null=True)
    spatial_res_value = models.CharField(max_length=100, null=True)
    is_broken = models.BooleanField(default=False)
    is_custom = models.BooleanField(default=False)
    is_inspire_conform = models.BooleanField(default=False)
    has_inspire_downloads = models.BooleanField(default=False)
    bounding_geometry = models.PolygonField(null=True, blank=True)

    # security
    is_secured = models.BooleanField(default=False)

    # capabilities
    dimension = models.CharField(max_length=100, null=True)
    authority_url = models.CharField(max_length=255, null=True)
    metadata_url = models.CharField(max_length=255, null=True)

    # other
    keywords = models.ManyToManyField(Keyword)
    categories = models.ManyToManyField('Category')
    reference_system = models.ManyToManyField('ReferenceSystem')
    metadata_type = models.ForeignKey('MetadataType', on_delete=models.DO_NOTHING, null=True, blank=True)
    hits = models.IntegerField(default=0)

    ## for ISO metadata
    dataset_id = models.CharField(max_length=255, null=True, blank=True)
    dataset_id_code_space = models.CharField(max_length=255, null=True, blank=True)

    related_metadata = models.ManyToManyField(MetadataRelation)
    origin = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.keywords_list = []
        self.reference_system_list = []

    def __str__(self):
        return self.title

    def get_current_capability_xml(self, version_param: str):
        """ Getter for the capability xml of the current status of this metadata object.

        If there is no capability document available (maybe the capabilities of a subelement of a service are requested),
        the capabilities xml will be generated and persisted to the database to increase the speed of another request.

        Args:
            version_param (str): The version parameter for which the capabilities shall be built
        Returns:

        """
        from service.helper import service_helper
        cap_doc = None
        try:
            # Try to fetch an existing Document record from the db
            cap_doc = Document.objects.get(related_metadata=self)

            if cap_doc.current_capability_document is None:
                # Well, there is one but no current_capability_document is found inside
                raise ObjectDoesNotExist
        except ObjectDoesNotExist as e:
            # This means we have no capability document in the db or the value is set to None.
            # This is possible for subelements of a service, which (usually) do not have an own capability document.
            # We create a capability document on the fly for this metadata object and persist it for another call.
            cap_xml = self._create_capability_xml(version_param)
            if cap_doc is None:
                cap_doc = Document(
                    related_metadata=self,
                    original_capability_document=cap_xml,
                    current_capability_document=cap_xml,
                )
            else:
                cap_doc.current_capability_document = cap_xml

            # Do not forget to proxy the links inside the document, if needed
            if self.use_proxy_uri:
                version_param_enum = service_helper.resolve_version_enum(version=version_param)
                cap_doc.set_proxy(use_proxy=True, force_version=version_param_enum, auto_save=False)

            # cap_doc.save() #ToDo: Comment back in!
        return cap_doc.current_capability_document

    def _create_capability_xml(self, force_version: str = None):
        """ Creates a capability xml from the current state of the service object

        Args:
            force_version (str): The OGC standard version that has to be used for xml generating
        Returns:
             xml (str): The xml document as string
        """
        from service.helper.ogc.capabilities_builder import CapabilityXMLBuilder

        capabilty_builder = CapabilityXMLBuilder(metadata=self, force_version=force_version)
        xml = capabilty_builder.generate_xml()
        return xml

    def get_external_authentication_object(self):
        """ Returns the external authentication object, if one exists

        If none exists, None will be returned

        Returns:
             ext_auth (ExternalAuthentication) | None
        """
        ext_auth = None
        try:
            ext_auth = self.external_authentication
        except ObjectDoesNotExist:
            pass
        return ext_auth

    def get_related_dataset_metadata(self):
        """ Returns a related dataset metadata record.

        If none exists, None is returned

        Returns:
             dataset_md (Metadata) | None
        """
        try:
            dataset_md = MetadataRelation.objects.get(
                metadata_from=self,
                metadata_to__metadata_type__type=OGCServiceEnum.DATASET.value
            )
            dataset_md = dataset_md.metadata_to
            return dataset_md
        except ObjectDoesNotExist as e:
            return None

    def get_remote_original_capabilities_document(self, version: str):
        """ Fetches the original capabilities document from the remote server.

        Returns:
             doc (str): The xml document as string
        """
        if version is None or len(version) == 0:
            raise ValueError()

        doc = None
        if self.has_external_authentication():
            ext_auth = self.external_authentication
            crypto_handler = CryptoHandler()
            key = crypto_handler.get_key_from_file(self.id)
            ext_auth.decrypt(key)
        else:
            ext_auth = None

        uri = self.capabilities_original_uri
        uri = utils.set_uri_GET_param(uri, "version", version)
        conn = CommonConnector(url=uri, external_auth=ext_auth)
        conn.load()
        if conn.status_code == 200:
            doc = conn.content
        else:
            raise ConnectionError()
        return doc

    def has_external_authentication(self):
        """ Checks whether the metadata has a related ExternalAuthentication set

        Returns:
             True | False
        """
        try:
            tmp = self.external_authentication
            return True
        except ObjectDoesNotExist:
            return False

    @transaction.atomic
    def increase_hits(self):
        """ Increases the hit counter of the metadata

        Returns:
             Nothing
        """
        # increase itself
        self.hits += 1

        # Only if whole service was called, increase the children hits as well
        if self.metadata_type.type == MetadataEnum.SERVICE.value:

            # wms children
            if self.service.servicetype.name == 'wms':
                children = self.service.child_service.all()
                for child in children:
                    child.metadata.hits += 1
                    child.metadata.save()

            elif self.service.servicetype.name == 'wfs':
                featuretypes = self.service.featuretypes.all()
                for f_t in featuretypes:
                    f_t.metadata.hits += 1
                    f_t.metadata.save()

        self.save()

    def delete(self, using=None, keep_parents=False):
        """ Overwriting of the regular delete function

        Checks if the current processed metadata is part of a MetadataRelation, which indicates, that it is still used
        somewhere else, maybe by another service. If there is only one MetadataRelation found for this metadata record,
        we can delete it safely..

        Args:
            using: The regular 'using' parameter
            keep_parents: The regular 'keep_parents' parameter
        Returns:
            nothing
        """
        # check for SecuredOperations
        if self.is_secured:
            sec_ops = self.secured_operations.all()
            sec_ops.delete()

        # remove externalAuthentication object if it exists
        try:
            self.external_authentication.delete()
        except ObjectDoesNotExist:
            pass

        # check if there are MetadataRelations on this metadata record
        # if so, we can not remove it until these relations aren't used anymore
        dependencies = MetadataRelation.objects.filter(
            metadata_to=self
        )
        if dependencies.count() > 1:
            # if there are more than one dependency, we should not remove it
            # the one dependency we can expect at least is the relation to the current metadata record
            return
        else:
            # if we have one or less relations to this metadata record, we can remove it anyway
            super().delete(using, keep_parents)

    def get_service_type(self):
        """ Performs a check on which service type is described by the metadata record

        Returns:
             service_type (str): The service type as string ('wms' or 'wfs')
        """
        service_type = None
        if self.is_root():
            return self.service.servicetype.name
        elif self.metadata_type.type == 'layer':
            service_type = 'wms'
        elif self.metadata_type.type == 'featuretype':
            service_type = 'wfs'
        return service_type

    def get_service_version(self):
        """ Returns the service version

        Returns:
             The service version
        """
        # Non root elements have to be handled differently, since FeatureTypes are not Service instances and always use
        # their parent_service as Service information holder
        if not self.is_root():
            if self.get_service_type() == OGCServiceEnum.WFS.value:
                service = FeatureType.objects.get(
                    metadata=self
                ).parent_service
            elif self.get_service_type() == OGCServiceEnum.WMS.value:
                service = self.service.parent_service
            else:
                raise TypeError(PARAMETER_ERROR.format("SERVICE"))
        else:
            service = self.service
        service_version = service.servicetype.version
        for v in OGCServiceVersionEnum:
            if v.value == service_version:
                return v
        return service_version

    def find_max_bounding_box(self):
        """ Returns the largest bounding box of all children

        Saves the found bounding box to bounding_geometry for faster access

        Returns:

        """
        children = self.service.child_service.all()
        max_box = self.bounding_geometry
        for child in children:
            bbox = child.layer.bbox_lat_lon
            if max_box is None:
                max_box = bbox
            else:
                ba = bbox.area
                ma = max_box.area
                if ba > ma:
                    max_box = bbox

        if max_box is None:
            max_box = DEFAULT_SERVICE_BOUNDING_BOX
        if max_box.area == 0:
            # if this element and it's children does not provide a bounding geometry, we simply take the one from the
            # whole service to avoid the map flipping somewhere else on the planet
            return self.service.parent_service.metadata.find_max_bounding_box()
        return max_box

    def is_root(self):
        """ Checks whether the metadata describes a root service or a layer/featuretype

        Returns:
             is_root (bool): True if there is no parent service to the described service, False otherwise
        """
        return self.metadata_type.type == 'service'

    def _restore_layer_md(self, service, identifier: str = None):
        """ Private function for retrieving single layer metadata

        Args:
            service (OGCWebMapService): An empty OGCWebMapService object to load and parse the metadata
            identifier (str): The identifier string of the layer
        Returns:
             nothing, it changes the Metadata object itself
        """
        from service.helper import service_helper
        # parse single layer
        identifier = self.service.layer.identifier
        layer = service.get_layer_by_identifier(identifier)
        self.title = layer.title
        self.abstract = layer.abstract
        self.is_custom = False
        self.keywords.clear()
        for kw in layer.capability_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        original_iso_links = [x.uri for x in layer.iso_metadata]
        for related_iso in self.related_metadata.all():
            md_link = related_iso.metadata_to.metadata_url
            if md_link not in original_iso_links:
                related_iso.metadata_to.delete()
                related_iso.delete()

        # restore partially capabilities document
        if self.is_root():
            rel_md = self
        else:
            rel_md = self.service.parent_service.metadata
        cap_doc = Document.objects.get(related_metadata=rel_md)
        cap_doc.restore_subelement(identifier)
        return

    def _restore_feature_type_md(self, service, identifier: str = None, external_auth: ExternalAuthentication = None):
        """ Private function for retrieving single featuretype metadata

        Args:
            service (OGCWebMapService): An empty OGCWebMapService object to load and parse the metadata
            identifier (str): The identifier string of the layer
        Returns:
             nothing, it changes the Metadata object itself
        """
        from service.helper import service_helper
        # parse single layer
        identifier = self.identifier
        f_t = service.get_feature_type_by_identifier(identifier, external_auth=external_auth)
        f_t_obj = f_t.get("feature_type", None)
        f_t_iso_links = f_t.get("dataset_md_list", [])
        self.title = f_t_obj.metadata.title
        self.abstract = f_t_obj.metadata.abstract
        self.is_custom = False
        self.keywords.clear()
        for kw in f_t_obj.metadata.keywords_list:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        for related_iso in self.related_metadata.all():
            md_link = related_iso.metadata_to.metadata_url
            if md_link not in f_t_iso_links:
                related_iso.metadata_to.delete()
                related_iso.delete()

        # restore partially capabilities document
        if self.is_root():
            rel_md = self
        else:
            rel_md = self.featuretype.parent_service.metadata
        cap_doc = Document.objects.get(related_metadata=rel_md)
        cap_doc.restore_subelement(identifier)
        return

    def _restore_wms(self, identifier: str = None, external_auth: ExternalAuthentication = None):
        """ Restore the metadata of a wms service

        Args;
            identifier (str): Identifies which layer should be restored.
        Returns:
             nothing
        """
        from service.helper.ogc.wms import OGCWebMapServiceFactory
        from service.helper import service_helper
        service_version = service_helper.resolve_version_enum(self.service.servicetype.version)
        service = None
        service = OGCWebMapServiceFactory()
        service = service.get_ogc_wms(version=service_version, service_connect_url=self.capabilities_original_uri)
        service.get_capabilities()
        service.create_from_capabilities(metadata_only=True, external_auth=external_auth)

        # check if whole service shall be restored or single layer
        if not self.is_root():
            return self._restore_layer_md(service, identifier)

        self.title = service.service_identification_title
        self.abstract = service.service_identification_abstract
        self.access_constraints = service.service_identification_accessconstraints
        keywords = service.service_identification_keywords
        self.keywords.clear()
        for kw in keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        # by default no categories
        self.categories.clear()
        self.is_custom = False
        self.use_proxy_uri = False

        cap_doc = Document.objects.get(related_metadata=self)
        cap_doc.restore()

    def _restore_wfs(self, identifier: str = None, external_auth: ExternalAuthentication = None):
        """ Restore the metadata of a wfs service

        Args;
            identifier (str): Identifies which layer should be restored.
        Returns:
             nothing
        """
        from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
        from service.helper import service_helper

        # Prepare 'service' for further handling
        # If no identifier is provided, we deal with a root metadata
        is_root = identifier is None
        if is_root:
            service = self.service
        else:
            service = self.featuretype.service
        service_version = service_helper.resolve_version_enum(service.servicetype.version)
        service_tmp = OGCWebFeatureServiceFactory()
        service_tmp = service_tmp.get_ogc_wfs(version=service_version, service_connect_url=self.capabilities_original_uri)
        if service_tmp is None:
            return
        service_tmp.get_capabilities()
        service_tmp.create_from_capabilities(metadata_only=True)
        # check if whole service shall be restored or single layer
        if not self.is_root():
            return self._restore_feature_type_md(service_tmp, identifier, external_auth=external_auth)

        self.title = service_tmp.service_identification_title
        self.abstract = service_tmp.service_identification_abstract
        self.access_constraints = service_tmp.service_identification_accessconstraints
        keywords = service_tmp.service_identification_keywords
        self.keywords.clear()
        for kw in keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        # by default no categories
        self.categories.clear()
        self.is_custom = False
        self.use_proxy_uri = False

        cap_doc = Document.objects.get(related_metadata=service.metadata)
        cap_doc.restore()

    def restore(self, identifier: str = None, external_auth: ExternalAuthentication = None):
        """ Load original metadata from capabilities and ISO metadata

        Args:
            identifier (str): The identifier of a featureType or Layer (in xml often named 'name')
        Returns:
             nothing
        """

        # identify whether this is a wfs or wms (we need to handle them in different ways)
        service_type = self.get_service_type()
        if service_type == OGCServiceEnum.WFS.value:
            self._restore_wfs(identifier, external_auth=external_auth)
        elif service_type == OGCServiceEnum.WMS.value:
            self._restore_wms(identifier, external_auth=external_auth)

        # Subelements like layers or featuretypes might have own capabilities documents. Delete them on restore!
        if not self.is_root():
            related_docs = Document.objects.filter(
                related_metadata=self
            )
            for doc in related_docs:
                doc.clear_current_capability_document()

    def get_related_metadata_uris(self):
        """ Generates a list of all related metadata online links and returns them

        Returns:
             links (list): A list containing all online links of related metadata
        """
        rel_mds = self.related_metadata.all()
        links = []
        for md in rel_mds:
            links.append(md.metadata_to.metadata_url)
        return links

    def _set_document_secured(self, is_secured: bool):
        """ Fetches the metadata documents and sets the secured uris for all operations

        Args:
            is_secured (bool): Whether the operations should be secured or not
        Returns:
            nothing
        """
        try:
            cap_doc = Document.objects.get(
                related_metadata=self
            )
            cap_doc.set_proxy(is_secured)
        except ObjectDoesNotExist:
            pass

    def set_documents_active_status(self, is_active: bool):
        """ Sets the active status for related documents

        Args:
            is_active (bool): Whether the documents are active or not
        Returns:

        """
        docs = Document.objects.filter(
            related_metadata=self
        )
        for doc in docs:
            doc.is_active = is_active
            doc.save()


    def set_logging(self, logging: bool):
        """ Set the metadata logging flag to a new value

        Args:
            logging (bool): Whether the metadata shall be logged or not
        Returns:
        """
        if self.use_proxy_uri:
            self.log_proxy_access = logging

            # If the metadata shall be logged, all of it's subelements shall be logged as well!
            child_mds = Metadata.objects.filter(service__parent_service=self.service)
            for child_md in child_mds:
                child_md.log_proxy_access = logging
                child_md.save()

            self.save()

    def set_proxy(self, use_proxy: bool):
        """ Set the metadata proxy to a new value.

        Iterates over subelements.

        Args:
            use_proxy (bool): Whether to use a proxy or not
        Returns:
        """
        if not self.is_root():
            root_md = self.service.parent_service.metadata
        else:
            root_md = self

        # change capabilities document
        root_md_doc = Document.objects.get(related_metadata=root_md)
        root_md_doc.set_proxy(use_proxy)

        self.use_proxy_uri = use_proxy

        # If md uris shall be tunneled using the proxy, we need to make sure that all metadata elements of the service are aware of this!
        service_type = self.get_service_type()
        subelements = []
        if service_type == OGCServiceEnum.WFS.value:
            subelements = self.service.featuretypes.all()
        elif service_type == OGCServiceEnum.WMS.value:
            subelements = Layer.objects.filter(parent_service=self.service)

        for subelement in subelements:
            subelement_md = subelement.metadata
            subelement_md.use_proxy_uri = self.use_proxy_uri
            subelement_md.save()

            # Remove current_capability_documents that are related to this subelement
            docs = Document.objects.filter(
                related_metadata=subelement_md
            )
            for doc in docs:
                doc.clear_current_capability_document()
        self.save()

    def set_secured(self, is_secured: bool):
        """ Set is_secured to a new value.

        Iterates over all children for the same purpose.
        Activates use_proxy automatically!

        Args:
            is_secured (bool): The new value for is_secured
        Returns:

        """
        self.is_secured = is_secured
        if not is_secured and self.use_proxy_uri:
            # secured access shall be disabled, but use_proxy is still enabled
            # we keep the use_proxy_uri on True!
            self.use_proxy_uri = True
        else:
            self.use_proxy_uri = is_secured
        self._set_document_secured(self.use_proxy_uri)

        md_type = self.metadata_type.type

        children = []
        if md_type == MetadataEnum.SERVICE.value or md_type == MetadataEnum.LAYER.value:
            if self.service.servicetype.name == OGCServiceEnum.WMS.value:
                parent_service = self.service
                children = Metadata.objects.filter(
                    service__parent_service=parent_service
                )
                for child in children:
                    child._set_document_secured(self.use_proxy_uri)

            elif self.service.servicetype.name == OGCServiceEnum.WFS.value:
                children = [ft.metadata for ft in self.service.featuretypes.all()]

            for child in children:
                child.is_secured = is_secured
                child.use_proxy_uri = self.use_proxy_uri
                child.save()

        elif md_type == MetadataEnum.FEATURETYPE.value:
            # a featuretype does not have children - we can skip this case!
            pass
        self.save()


class MetadataType(models.Model):
    type = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.type


class Document(Resource):
    related_metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE)
    original_capability_document = models.TextField(null=True, blank=True)
    current_capability_document = models.TextField(null=True, blank=True)
    service_metadata_document = models.TextField(null=True, blank=True)
    dataset_metadata_document = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.related_metadata.title

    def set_proxy(self, use_proxy: bool, force_version: OGCServiceVersionEnum=None, auto_save: bool=True):
        """ Sets different elements inside the document on a secured level

        Args:
            use_proxy (bool): Whether to use a proxy or not
            auto_save (bool): Whether to directly save the modified document or not
        Returns:
        """
        self.set_dataset_metadata_secured(use_proxy, force_version=force_version, auto_save=auto_save)
        self.set_legend_url_secured(use_proxy, force_version=force_version, auto_save=auto_save)
        self.set_operations_secured(use_proxy, force_version=force_version, auto_save=auto_save)

    def _set_wms_operations_secured(self, xml_obj, uri: str, is_secured: bool):
        """ Change external links to internal for wms operations

        Args:
            xml_obj: The xml document object
            uri: The new uri to be set, if secured
            is_secured: Whether the document shall be secured or not
        Returns:
             Nothing, directly works on the xml_obj
        """
        request_objs = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Request")
            , xml_obj
        )
        request_objs = request_objs.getchildren()
        service = self.related_metadata.service
        op_uri_dict = {
            "GetMap": {
                "Get": service.get_map_uri_GET,
                "Post": service.get_map_uri_POST,
            },
            "GetFeatureInfo": {
                "Get": service.get_feature_info_uri_GET,
                "Post": service.get_feature_info_uri_POST,
            },
            "DescribeLayer": {
                "Get": service.describe_layer_uri_GET,
                "Post": service.describe_layer_uri_POST,
            },
            "GetLegendGraphic": {
                "Get": service.get_legend_graphic_uri_GET,
                "Post": service.get_legend_graphic_uri_POST,
            },
            "GetStyles": {
                "Get": service.get_styles_uri_GET,
                "Post": service.get_styles_uri_POST,
            },
        }

        for op in request_objs:

            # skip GetCapabilities - it is already set to another internal link
            if OGCOperationEnum.GET_CAPABILITIES.value in op.tag:
                continue

            uri_dict = op_uri_dict.get(op.tag, "")
            http_operations = ["Get", "Post"]

            for http_operation in http_operations:
                res_objs = xml_helper.try_get_element_from_xml(
                    ".//{}/".format(GENERIC_NAMESPACE_TEMPLATE.format(http_operation)) + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource")
                    , op
                )

                if not is_secured:
                    # overwrite uri
                    uri = uri_dict.get(http_operation, "")

                for res_obj in res_objs:
                    xml_helper.write_attribute(
                        res_obj,
                        attrib="{http://www.w3.org/1999/xlink}href",
                        txt=uri
                    )

    def _set_wfs_1_0_0_operations_secured(self, xml_obj, uri: str, is_secured: bool):
        """ Change external links to internal for wfs 1.0.0 operations

        Args:
            xml_obj: The xml document object
            uri: The new uri to be set, if secured
            is_secured: Whether the document shall be secured or not
        Returns:
             Nothing, directly works on the xml_obj
        """
        operation_objs = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Request")
            , xml_obj
        )
        try:
            service = self.related_metadata.service
        except ObjectDoesNotExist:
            service = FeatureType.objects.get(
                metadata=self.related_metadata
            ).parent_service
        op_uri_dict = {
            OGCOperationEnum.DESCRIBE_FEATURE_TYPE.value: {
                "Get": service.describe_layer_uri_GET,
                "Post": service.describe_layer_uri_POST,
            },
            OGCOperationEnum.GET_FEATURE.value: {
                "Get": service.get_feature_info_uri_GET,
                "Post": service.get_feature_info_uri_POST,
            },
            OGCOperationEnum.GET_PROPERTY_VALUE.value: {
                "Get": service.get_property_value_uri_GET,
                "Post": service.get_property_value_uri_POST,
            },
            OGCOperationEnum.LIST_STORED_QUERIES.value: {
                "Get": service.list_stored_queries_uri_GET,
                "Post": service.list_stored_queries_uri_POST,
            },
            OGCOperationEnum.DESCRIBE_STORED_QUERIES.value: {
                "Get": service.describe_stored_queries_uri_GET,
                "Post": service.describe_stored_queries_uri_POST,
            },
        }

        for op in operation_objs:
            # skip GetCapabilities - it is already set to another internal link
            name = op.tag
            if OGCOperationEnum.GET_CAPABILITIES.value in name:
                continue
            if not is_secured:
                uri = op_uri_dict.get(name, {"Get": None, "Post": None})
            http_objs = xml_helper.try_get_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP"), op)
            for http_obj in http_objs:
                requ_objs = http_obj.getchildren()
                for requ_obj in requ_objs:
                    xml_helper.write_attribute(
                        requ_obj,
                        attrib="onlineResource",
                        txt=uri
                    )

    def _set_wfs_operations_secured(self, xml_obj, uri: str, is_secured: bool):
        """ Change external links to internal for wfs operations

        Args:
            xml_obj: The xml document object
            uri: The new uri to be set, if secured
            is_secured: Whether the document shall be secured or not
        Returns:
             Nothing, directly works on the xml_obj
        """
        operation_objs = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation"), xml_obj)

        try:
            service = self.related_metadata.service
        except ObjectDoesNotExist:
            service = FeatureType.objects.get(
                metadata=self.related_metadata
            ).parent_service

        op_uri_dict = {
            "DescribeFeatureType": {
                "Get": service.describe_layer_uri_GET,
                "Post": service.describe_layer_uri_POST,
            },
            "GetFeature": {
                "Get": service.get_feature_info_uri_GET,
                "Post": service.get_feature_info_uri_POST,
            },
            "GetPropertyValue": {
                "Get": service.get_property_value_uri_GET,
                "Post": service.get_property_value_uri_POST,
            },
            "ListStoredQueries": {
                "Get": service.list_stored_queries_uri_GET,
                "Post": service.list_stored_queries_uri_POST,
            },
            "DescribeStoredQueries": {
                "Get": service.describe_stored_queries_uri_GET,
                "Post": service.describe_stored_queries_uri_POST,
            },
            "GetGmlObject": {
                "Get": service.get_gml_objct_uri_GET,
                "Post": service.get_gml_objct_uri_POST,
            },
        }

        fallback_uri = service.get_feature_info_uri_GET

        for op in operation_objs:
            # skip GetCapabilities - it is already set to another internal link
            name = xml_helper.try_get_attribute_from_xml_element(op, "name")
            if name == OGCOperationEnum.GET_CAPABILITIES.value or name is None:
                continue

            http_operations = ["Get", "Post"]

            for http_operation in http_operations:

                if not is_secured:
                    uri = op_uri_dict.get(name, {}).get(http_operation, None) or fallback_uri

                http_objs = xml_helper.try_get_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") + "/" + GENERIC_NAMESPACE_TEMPLATE.format(http_operation), op)

                for http_obj in http_objs:
                    xml_helper.write_attribute(
                        http_obj,
                        attrib="{http://www.w3.org/1999/xlink}href",
                        txt=uri
                    )

    def _set_wms_1_0_0_operation_secured(self, xml_obj, uri: str, is_secured: bool):
        """ Change external links to internal for wms 1.0.0 operations

        Args:
            xml_obj: The xml document object
            uri: The new uri to be set, if secured
            is_secured: Whether the document shall be secured or not
        Returns:
             Nothing, directly works on the xml_obj
        """
        request_objs = xml_helper.try_get_single_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capability") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("Request")
            , xml_obj
        )
        request_objs = request_objs.getchildren()
        service = self.related_metadata.service
        op_uri_dict = {
            "GetMap": {
                "Get": service.get_map_uri_GET,
                "Post": service.get_map_uri_POST,
            },
            "GetFeatureInfo": {
                "Get": service.get_feature_info_uri_GET,
                "Post": service.get_feature_info_uri_POST,
            },
            "DescribeLayer": {
                "Get": service.describe_layer_uri_GET,
                "Post": service.describe_layer_uri_POST,
            },
            "GetLegendGraphic": {
                "Get": service.get_legend_graphic_uri_GET,
                "Post": service.get_legend_graphic_uri_POST,
            },
            "GetStyles": {
                "Get": service.get_styles_uri_GET,
                "Post": service.get_styles_uri_POST,
            },
        }

        for op in request_objs:

            # skip GetCapabilities - it is already set to another internal link
            if OGCOperationEnum.GET_CAPABILITIES.value in op.tag:
                continue

            uri_dict = op_uri_dict.get(op.tag, "")
            http_operations = ["Get", "Post"]

            for http_operation in http_operations:
                res_objs = xml_helper.try_get_element_from_xml(".//{}".format(http_operation), op)

                if not is_secured:
                    # overwrite uri
                    uri = uri_dict.get(http_operation, "")

                for res_obj in res_objs:
                    xml_helper.write_attribute(
                        res_obj,
                        attrib="onlineResource",
                        txt=uri
                    )

    def set_capabilities_secured(self, auto_save: bool=True):
        """ Change external links to internal for service capability document call

        Args:
            auto_save (bool): Whether the document shall be directly saved or not
        Returns:

        """

        # change some external linkage to internal links for the current_capability_document
        uri = SERVICE_OPERATION_URI_TEMPLATE.format(self.related_metadata.id)
        xml = xml_helper.parse_xml(self.original_capability_document)

        # wms and wfs have to be handled differently!
        # Furthermore each standard has a different handling of attributes and elements ...
        service_type = self.related_metadata.get_service_type()
        service_version = self.related_metadata.get_service_version().value

        if service_type == OGCServiceEnum.WMS.value:

            if service_version == "1.0.0":
                # additional things to change for WMS 1.0.0
                xml_helper.write_text_to_element(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Service") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    uri
                )
                http_methods = ["Get", "Post"]
                for method in http_methods:
                    xml_helper.write_attribute(
                        xml,
                        "//" + GENERIC_NAMESPACE_TEMPLATE.format("Capabilities") +
                        "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCPType") +
                        "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                        "/" + GENERIC_NAMESPACE_TEMPLATE.format(method),
                        "onlineResource",
                        uri)

            else:
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Service") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    "{http://www.w3.org/1999/xlink}href", uri)
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("GetCapabilities") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCPType") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Get") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    "{http://www.w3.org/1999/xlink}href",
                    uri)
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("GetCapabilities") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCPType") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Post") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    "{http://www.w3.org/1999/xlink}href",
                    uri)

        elif service_type == OGCServiceEnum.WFS.value:
            if service_version == "1.0.0":
                xml_helper.write_text_to_element(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Service") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    uri
                )
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation") + "[@name='GetCapabilities']" +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Get"),
                    "onlineResource",
                    uri
                )
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation") + "[@name='GetCapabilities']" +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Post"),
                    "onlineResource",
                    uri
                )
            else:
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("ContactInfo") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
                    "{http://www.w3.org/1999/xlink}href",
                    uri
                )
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation") + "[@name='GetCapabilities']" +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Get"),
                    "{http://www.w3.org/1999/xlink}href",
                    uri
                )
                xml_helper.write_attribute(
                    xml,
                    "//" + GENERIC_NAMESPACE_TEMPLATE.format("Operation") + "[@name='GetCapabilities']" +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("DCP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP") +
                    "/" + GENERIC_NAMESPACE_TEMPLATE.format("Post"),
                    "{http://www.w3.org/1999/xlink}href",
                    uri
                )

        xml = xml_helper.xml_to_string(xml)
        self.current_capability_document = xml

        if auto_save:
            self.save()

    def set_operations_secured(self, is_secured: bool, force_version: OGCServiceVersionEnum, auto_save: bool=True):
        """ Change external links to internal for service operations

        Args:
            is_secured (bool): Whether the service is secured or not
            force_version (OGCServiceVersionEnum): Which version processing shall be forced
            auto_save (bool): Whether to directly save at the end of the function or not
        Returns:

        """
        xml_obj = xml_helper.parse_xml(self.current_capability_document)
        if is_secured:
            uri = SERVICE_OPERATION_URI_TEMPLATE.format(self.related_metadata.id)
        else:
            uri = ""
        _type = self.related_metadata.get_service_type()
        _version = force_version or self.related_metadata.get_service_version()
        if _type == OGCServiceEnum.WMS.value:
            if _version is OGCServiceVersionEnum.V_1_0_0:
                self._set_wms_1_0_0_operation_secured(xml_obj, uri, is_secured)
            else:
                self._set_wms_operations_secured(xml_obj, uri, is_secured)
        elif _type == OGCServiceEnum.WFS.value:
            if _version is OGCServiceVersionEnum.V_1_0_0:
                self._set_wfs_1_0_0_operations_secured(xml_obj, uri, is_secured)
            else:
                self._set_wfs_operations_secured(xml_obj, uri, is_secured)

        self.current_capability_document = xml_helper.xml_to_string(xml_obj)

        if auto_save:
            self.save()

    def set_dataset_metadata_secured(self, is_secured: bool, force_version: OGCServiceVersionEnum=None, auto_save: bool=True):
        """ Set or unsets the proxy for the dataset metadata uris

        Args:
            is_secured (bool): Whether the proxy shall be activated or deactivated
            force_version (OGCServiceVersionEnum): Which version processing shall be forced
            auto_save (bool): Whether to directly save at the end of the function or not
        Returns:
             nothing
        """
        cap_doc_curr = self.current_capability_document
        xml_obj = xml_helper.parse_xml(cap_doc_curr)
        service_version = force_version or self.related_metadata.get_service_version()
        service_type = self.related_metadata.get_service_type()
        is_wfs_1_0_0 = service_type == OGCServiceEnum.WFS.value and service_version is OGCServiceVersionEnum.V_1_0_0
        is_wfs_1_1_0 = service_type == OGCServiceEnum.WFS.value and service_version is OGCServiceVersionEnum.V_1_1_0

        # get <MetadataURL> xml elements
        if is_wfs_1_0_0 or is_wfs_1_1_0:
            xml_metadata_elements = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("MetadataURL"), xml_obj)
        else:
            xml_metadata_elements = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("MetadataURL") + "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"), xml_obj)

        # iterate over elements and change the uris
        for xml_metadata in xml_metadata_elements:
            attr = "{http://www.w3.org/1999/xlink}href"

            # get metadata url
            if is_wfs_1_0_0 or is_wfs_1_1_0:
                metadata_uri = xml_helper.try_get_text_from_xml_element(xml_metadata)
            else:
                metadata_uri = xml_helper.get_href_attribute(xml_metadata)
            own_uri_prefix = "{}{}".format(HTTP_OR_SSL, HOST_NAME)

            if not metadata_uri.startswith(own_uri_prefix):
                # find metadata record which matches the metadata uri
                try:
                    dataset_md_record = Metadata.objects.get(metadata_url=metadata_uri)
                    uri = SERVICE_DATASET_URI_TEMPLATE.format(dataset_md_record.id)
                except ObjectDoesNotExist:
                    # This is a bad situation... Only possible if the registered service has not been updated BUT the
                    # original remote service changed and maybe has a new - for us - unknown MetadataURL object.
                    # This is why we can't find it in our db. We simply have to set it to some placeholder, since the
                    # user has to update the service.
                    uri = "unknown"
            else:
                # this means we have our own proxy uri in here and want to restore the original one
                # metadata uri contains the proxy uri
                # so we need to extract the id from the uri!
                md_uri_list = metadata_uri.split("/")
                md_id = md_uri_list[len(md_uri_list) - 1]
                dataset_md_record = Metadata.objects.get(id=md_id)
                uri = dataset_md_record.metadata_url
            if is_wfs_1_0_0 or is_wfs_1_1_0:
                xml_helper.write_text_to_element(xml_metadata, txt=uri)
            else:
                xml_helper.set_attribute(xml_metadata, attr, uri)
        xml_obj_str = xml_helper.xml_to_string(xml_obj)
        self.current_capability_document = xml_obj_str

        if auto_save:
            self.save()

    def set_legend_url_secured(self, is_secured: bool, force_version:OGCServiceVersionEnum=None, auto_save: bool=True):
        """ Set or unsets the proxy for the style legend uris

        Args:
            is_secured (bool): Whether the proxy shall be activated or deactivated
            force_version (OGCServiceVersionEnum): Which version processing shall be forced
            auto_save (bool): Whether to directly save at the end of the function or not
        Returns:
             nothing
        """
        cap_doc_curr = self.current_capability_document
        xml_doc = xml_helper.parse_xml(cap_doc_curr)

        # get <LegendURL> elements
        xml_legend_elements = xml_helper.try_get_element_from_xml(
            "//" + GENERIC_NAMESPACE_TEMPLATE.format("LegendURL") +
            "/" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource"),
            xml_doc
        )
        attr = "{http://www.w3.org/1999/xlink}href"
        for xml_elem in xml_legend_elements:
            legend_uri = xml_helper.get_href_attribute(xml_elem)

            uri = None

            if is_secured and not legend_uri.startswith(ROOT_URL):
                layer_identifier = dict(urllib.parse.parse_qsl(legend_uri)).get("layer", None)
                parent_md = self.related_metadata

                if not self.related_metadata.is_root():
                    parent_md = self.related_metadata.service.parent_service.metadata

                style_id = Style.objects.get(
                    layer__parent_service__metadata=parent_md,
                    layer__identifier=layer_identifier
                ).id
                uri = SERVICE_LEGEND_URI_TEMPLATE.format(self.related_metadata.id, style_id)

            elif not is_secured and legend_uri.startswith(ROOT_URL):
                # restore the original legend uri by using the layer identifier
                style_id = legend_uri.split("/")[-1]
                uri = Style.objects.get(id=style_id).legend_uri

            if uri is not None:
                xml_helper.set_attribute(xml_elem, attr, uri)

        xml_doc_str = xml_helper.xml_to_string(xml_doc)
        self.current_capability_document = xml_doc_str

        if auto_save:
            self.save()

    def restore(self):
        """ We overwrite the current metadata xml with the original

        Returns:
             nothing
        """
        self.current_capability_document = self.original_capability_document
        self.save()

    def restore_subelement(self, identifier: str):
        """ Restores only the layer which matches the provided identifier

        Args:
            identifier (str): The identifier which matches a single layer in the document
        Returns:
             nothing
        """
        # only restored the layer and it's children
        cap_doc_curr_obj = xml_helper.parse_xml(self.current_capability_document)
        cap_doc_orig_obj = xml_helper.parse_xml(self.original_capability_document)

        xml_layer_obj_curr = xml_helper.find_element_where_text(cap_doc_curr_obj, identifier)[0]
        xml_layer_obj_orig = xml_helper.find_element_where_text(cap_doc_orig_obj, identifier)[0]

        # find position where original element existed
        parent_orig = xml_helper.get_parent(xml_layer_obj_orig)
        orig_index = parent_orig.index(xml_layer_obj_orig)

        # insert original element at the original index and remove current element (which now is at index + 1)
        parent_curr = xml_helper.get_parent(xml_layer_obj_curr)
        parent_curr.insert(orig_index, xml_layer_obj_orig)
        parent_curr.remove(xml_layer_obj_curr)

        self.current_capability_document = xml_helper.xml_to_string(cap_doc_curr_obj)
        self.save()

    def clear_current_capability_document(self):
        """ Sets the current_capability_document content to None

        Returns:

        """
        self.current_capability_document = None
        self.save()

class TermsOfUse(Resource):
    name = models.CharField(max_length=100)
    symbol_url = models.CharField(max_length=100)
    description = models.TextField()
    is_open_data = models.BooleanField(default=False)
    fees = models.CharField(max_length=100)


class CategoryOrigin(models.Model):
    name = models.CharField(max_length=255)
    uri = models.CharField(max_length=500)

    def __str__(self):
        return self.name


class Category(Resource):
    type = models.CharField(max_length=255)
    title_locale_1 = models.CharField(max_length=255, null=True)
    title_locale_2 = models.CharField(max_length=255, null=True)
    title_EN = models.CharField(max_length=255, null=True)
    description_locale_1 = models.TextField(null=True)
    description_locale_2 = models.TextField(null=True)
    description_EN = models.TextField(null=True)
    symbol = models.CharField(max_length=500, null=True)
    online_link = models.CharField(max_length=500, null=True)
    origin = models.ForeignKey(CategoryOrigin, on_delete=models.DO_NOTHING, null=True)

    def __str__(self):
        return self.title_EN + " (" + self.type + ")"


class ServiceType(models.Model):
    name = models.CharField(max_length=100)
    version = models.CharField(max_length=100)
    specification = models.URLField(blank=False, null=True)

    def __str__(self):
        return self.name


class Service(Resource):
    metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE, related_name="service")
    parent_service = models.ForeignKey('self', on_delete=models.CASCADE, related_name="child_service", null=True, default=None, blank=True)
    published_for = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, related_name="published_for", null=True, default=None, blank=True)
    servicetype = models.ForeignKey(ServiceType, on_delete=models.DO_NOTHING, blank=True)
    categories = models.ManyToManyField(Category, blank=True)
    is_root = models.BooleanField(default=False)
    availability = models.DecimalField(decimal_places=2, max_digits=4, default=0.0)
    is_available = models.BooleanField(default=False)


    get_capabilities_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    get_capabilities_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    get_map_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    get_map_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    get_feature_info_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    get_feature_info_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    describe_layer_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    describe_layer_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    get_legend_graphic_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    get_legend_graphic_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    get_styles_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    get_styles_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    transaction_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    transaction_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    get_property_value_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    get_property_value_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    list_stored_queries_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    list_stored_queries_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    describe_stored_queries_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    describe_stored_queries_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    get_gml_objct_uri_GET = models.CharField(max_length=1000, null=True, blank=True)
    get_gml_objct_uri_POST = models.CharField(max_length=1000, null=True, blank=True)

    formats = models.ManyToManyField('MimeType', blank=True)

    # used to store ows linked_service_metadata until parsing
    # will not be part of the db
    linked_service_metadata = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.root_layer = None
        self.feature_type_list = []
        self.formats_list = []
        self.categories_list = []

    def __str__(self):
        return str(self.id)

    def perform_single_element_securing(self, element, is_secured: bool, group: Group, operation: RequestOperation, group_polygons: dict, sec_op: SecuredOperation):
        """ Secures a single element

        Args:
            element: The element which shall be secured
            is_secured (bool): Whether to secure the element or not
            group (Group): The group which is allowed to perform an operation
            operation (RequestOperation): The operation which can be performed by the groups
            group_polygons (dict): The polygons which restrict the access for the group
        Returns:

        """
        element.metadata.is_secured = is_secured
        if is_secured:

            if sec_op is None:
                sec_op = SecuredOperation()
                sec_op.operation = operation
                sec_op.allowed_group = group
            else:
                sec_op = SecuredOperation.objects.get(
                    secured_metadata=element.metadata,
                    operation=operation,
                    allowed_group=group
                )

            poly_list = []
            for group_polygon in group_polygons:
                poly_str = group_polygon.get("geometry", group_polygon).get("coordinates", [None])[0]
                tmp_poly = Polygon(poly_str)
                poly_list.append(tmp_poly)

            sec_op.bounding_geometry = GeometryCollection(poly_list)
            sec_op.save()
            element.metadata.secured_operations.add(sec_op)
        else:
            for sec_op in element.metadata.secured_operations.all():
                sec_op.delete()
            element.metadata.secured_operations.clear()
        element.metadata.save()
        element.save()

    def _recursive_secure_sub_layers(self, current, is_secured: bool, group: Group, operation: RequestOperation, group_polygons: dict, secured_operation: SecuredOperation):
        """ Recursive implementation of securing all sub layers of a current layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            group (Group): The group which is allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
            group_polygons (dict): The polygons which restrict the access for the group
        Returns:
             nothing
        """
        self.perform_single_element_securing(current, is_secured, group, operation, group_polygons, secured_operation)

        for layer in current.child_layer.all():
            self._recursive_secure_sub_layers(layer, is_secured, group, operation, group_polygons, secured_operation)

    def _secure_sub_layers(self, is_secured: bool, group: Group, operation: RequestOperation, group_polygons: dict, secured_operation: SecuredOperation):
        """ Secures all sub layers of this layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            group (Group): The group which is allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
            group_polygons (dict): The polygons which restrict the access for the group
        Returns:
             nothing
        """
        if self.is_root:
            # get the first layer in this service
            start_element = Layer.objects.get(
                parent_service=self,
                parent_layer=None,
            )
        else:
            # simply get the layer which is described by the given metadata
            start_element = Layer.objects.get(
                metadata=self.metadata
            )
        self._recursive_secure_sub_layers(start_element, is_secured, group, operation, group_polygons, secured_operation)

    def _secure_feature_types(self, is_secured: bool, group: Group, operation: RequestOperation, group_polygons: dict, secured_operation: SecuredOperation):
        """ Secures all sub layers of this layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            group (Group): The group which is allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
            group_polygons (dict): The polygons which restrict the access for the group
        Returns:
             nothing
        """
        if self.is_root:
            elements = self.featuretypes.all()
            for element in elements:
                self.perform_single_element_securing(element, is_secured, group, operation, group_polygons, secured_operation)

    def secure_sub_elements(self, is_secured: bool, group: Group, operation: RequestOperation, group_polygons: dict, secured_operation: SecuredOperation):
        """ Secures all sub elements of this layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            group (Group): The group which is allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
            group_polygons (dict): The polygons which restrict the access for the group
        Returns:
             nothing
        """
        if self.servicetype.name == OGCServiceEnum.WMS.value:
            self._secure_sub_layers(is_secured, group, operation, group_polygons, secured_operation)
        elif self.servicetype.name == OGCServiceEnum.WFS.value:
            self._secure_feature_types(is_secured, group, operation, group_polygons, secured_operation)

    @transaction.atomic
    def delete_child_data(self, child):
        """ Delete all layer data like related iso metadata

        Args:
            layer (Layer): The current layer object
        Returns:
            nothing
        """
        # remove related metadata
        iso_mds = MetadataRelation.objects.filter(metadata_from=child.metadata)
        for iso_md in iso_mds:
            md_2 = iso_md.metadata_to
            md_2.delete()
            iso_md.delete()
        if isinstance(child, FeatureType):
            # no other way to remove feature type metadata on service deleting
            child.metadata.delete()
        child.delete()

    @transaction.atomic
    def delete(self, using=None, keep_parents=False):
        """ Overwrites default delete method

        Recursively remove children

        Args;
            using:
            keep_parents:
        Returns:
        """
        # remove related metadata
        linked_mds = MetadataRelation.objects.filter(metadata_from=self.metadata)
        for linked_md in linked_mds:
            md_2 = linked_md.metadata_to
            md_2.delete()
            linked_md.delete()

        # remove subelements
        if self.servicetype.name == 'wms':
            layers = self.child_service.all()
            for layer in layers:
                self.delete_child_data(layer)
        elif self.servicetype.name == 'wfs':
            feature_types = self.featuretypes.all()
            for f_t in feature_types:
                self.delete_child_data(f_t)
        self.metadata.delete()
        super().delete()

    def __get_children(self, current, layers: list):
        """ Recursive appending of all layers

        Args:
            current (Layer): The current layer instance
            layers (list): The list of all collected layers so far
        Returns:
             nothing
        """
        layers.append(current)
        for layer in current.children_list:
            layers.append(layer)
            if len(layer.children_list) > 0:
                self.__get_children(layer, layers)

    def get_all_layers(self):
        """ Returns all layers in a list that can be found in this service

        NOTE: THIS IS ONLY USED FOR CHILDREN_LIST, WHICH SHOULD ONLY BE USED FOR NON-PERSISTED OBJECTS!!!

        Returns:
             layers (list): The layers
        """

        layers = []
        self.__get_children(self.root_layer, layers)
        return layers

    def activate_service(self, is_active: bool):
        """ Toggles the activity status of a service and it's metadata

        Args:
            is_active (bool): Whether the service shall be activated or not
        Returns:
             nothing
        """
        self.is_active = is_active
        self.metadata.is_active = is_active

        linked_mds = self.metadata.related_metadata.all()
        for md_relation in linked_mds:
            md_relation.metadata_to.is_active = is_active
            md_relation.metadata_to.save(update_last_modified=False)

        self.metadata.save(update_last_modified=False)
        self.save(update_last_modified=False)

    def persist_capabilities_doc(self, xml: str):
        """ Persists the capabilities document

        Args:
            xml (str): The xml document as string
        Returns:
             nothing
        """
        # save original capabilities document
        cap_doc = Document()
        cap_doc.original_capability_document = xml
        cap_doc.related_metadata = self.metadata
        cap_doc.set_capabilities_secured()


class Layer(Service):
    class Meta:
        ordering = ["position"]
    identifier = models.CharField(max_length=500, null=True)
    preview_image = models.CharField(max_length=100, blank=True, null=True)
    preview_extent = models.CharField(max_length=100, blank=True, null=True)
    preview_legend = models.CharField(max_length=100)
    parent_layer = models.ForeignKey("self", on_delete=models.CASCADE, null=True, related_name="child_layer")
    position = models.IntegerField(default=0)
    is_queryable = models.BooleanField(default=False)
    is_opaque = models.BooleanField(default=False)
    is_cascaded = models.BooleanField(default=False)
    scale_min = models.FloatField(default=0)
    scale_max = models.FloatField(default=0)
    bbox_lat_lon = models.PolygonField(default=Polygon(
        (
            (-90.0, -180.0),
            (-90.0, 180.0),
            (90.0, 180.0),
            (90.0, -180.0),
            (-90.0, -180.0),
        )
    ))
    iso_metadata = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.children_list = []
        self.dimension = None
        self.tmp_style = None  # holds the style before persisting

    def __str__(self):
        return str(self.identifier)

    def get_inherited_reference_systems(self):
        ref_systems = []
        ref_systems += list(self.metadata.reference_system.all())

        parent_layer = self.parent_layer
        while parent_layer is not None:
            parent_srs = parent_layer.metadata.reference_system.all()
            for srs in parent_srs:
                if srs not in ref_systems:
                    ref_systems.append(srs)
            parent_layer = parent_layer.parent_layer

        return ref_systems

    def get_inherited_bounding_geometry(self):
        """ Returns the biggest bounding geometry of the service.

        Bounding geometries shall be inherited. We do not persist them directly into the layer objects, since we might
        lose the geometry, that is specified by the single layer object.
        This function walks all the way up to the root layer of the service and returns the biggest bounding geometry.
        Since upper layer geometries must cover the ones of their children, these big geometry includes the children ones.

        Returns:
             bounding_geometry (Polygon): A geometry object
        """
        bounding_geometry = self.metadata.bounding_geometry
        parent_layer = self.parent_layer
        while parent_layer is not None:
            parent_geometry = parent_layer.metadata.bounding_geometry
            if bounding_geometry.area > 0:
                if parent_geometry.covers(bounding_geometry):
                    bounding_geometry = parent_geometry
            else:
                bounding_geometry = parent_geometry
            parent_layer = parent_layer.parent_layer
        return bounding_geometry


    def get_style(self):
        """ Simple getter for the style of the current layer

        Returns:
             styles (QuerySet): A query set containing all styles
        """
        return self.style.all()

    def get_children(self):
        """ Simple getter for the direct children of the current layer

        Returns:
             children (QuerySet): A query set containing all direct children layer of this layer
        """
        return self.child_layer.all()

    def delete_children_secured_operations(self, layer, operation, group):
        """ Walk recursive through all layers of wms and remove their secured operations

        The 'layer' will not be affected!

        Args:
            layer: The layer, which children shall be changed.
            operation: The RequestOperation of the SecuredOperation
            group: The group
        Returns:

        """
        for child_layer in layer.child_layer.all():
            sec_ops = SecuredOperation.objects.filter(
                secured_metadata=child_layer.metadata,
                operation=operation,
                allowed_group=group,
            )
            sec_ops.delete()
            self.delete_children_secured_operations(child_layer, operation, group)

    def activate_layer_recursive(self, new_status):
        """ Walk recursive through all layers of a wms and set the activity status new

        Args:
            root_layer: The root layer, where the recursion begins
            new_status: The new status that will be persisted
        Returns:
             nothing
        """
        self.metadata.is_active = new_status
        self.metadata.save()
        self.metadata.set_documents_active_status(new_status)
        self.is_active = new_status
        self.save()


        # check for all related metadata, we need to toggle their active status as well
        rel_md = self.metadata.related_metadata.all()
        for md in rel_md:
            dependencies = MetadataRelation.objects.filter(
                metadata_to=md.metadata_to,
                metadata_from__is_active=True,
            )
            if dependencies.count() >= 1 and md not in dependencies:
                # we still have multiple dependencies on this relation (besides us), we can not deactivate the metadata
                pass
            else:
                # since we have no more dependencies on this metadata, we can set it inactive
                md.metadata_to.is_active = new_status
                md.metadata_to.save()
                md.save()

        for layer in self.child_layer.all():
            layer.activate_layer_recursive(new_status)

    def _get_bottom_layers_recursive(self, parent, leaf_list: list):
        """ Runs a recursive search for all leaf layers.

        If a leaf layer is found, it will be added to layer_list

        Args:
            parent: The parent layer object
            leaf_list (list): The leafs
        Returns:
             nothing, directly changes leaf_list
        """
        layer_obj_children = parent.child_layer.all()
        for child in layer_obj_children:
            self._get_bottom_layers_recursive(child, leaf_list)
        if layer_obj_children.count() == 0:
            leaf_list.append(parent.identifier)

    def get_leaf_layers(self):
        """ Returns a list of all leaf layers.

        Leaf layers are the layers, which have no further children.

        Returns:
             leaf_layers (list): The leaf layers of a layer
        """
        leaf_layers = []
        layer_obj_children = self.child_layer.all()
        for child in layer_obj_children:
            self._get_bottom_layers_recursive(child, leaf_layers)
        return leaf_layers


class Module(Service):
    type = models.CharField(max_length=100)

    def __str__(self):
        return self.type


class ReferenceSystem(models.Model):
    code = models.CharField(max_length=100)
    prefix = models.CharField(max_length=255, default="EPSG:")
    version = models.CharField(max_length=50, default="9.6.1")

    def __str__(self):
        return self.code


class Dataset(Resource):
    time_begin = models.DateTimeField()
    time_end = models.DateTimeField()


class MimeType(Resource):
    operation = models.CharField(max_length=255, null=True)
    mime_type = models.CharField(max_length=500)

    def __str__(self):
        return self.mime_type


class Dimension(models.Model):
    layer = models.ForeignKey(Layer, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    units = models.CharField(max_length=255)
    default = models.CharField(max_length=255)
    nearest_value = models.CharField(max_length=255)
    current = models.CharField(max_length=255)
    extent = models.CharField(max_length=500)
    inherited = models.BooleanField()

    def __str__(self):
        return self.layer.name + ": " + self.name


class Style(models.Model):
    layer = models.ForeignKey(Layer, on_delete=models.CASCADE, related_name="style")
    name = models.CharField(max_length=255, null=True, blank=True)
    title = models.CharField(max_length=255, null=True, blank=True)
    legend_uri = models.CharField(max_length=500, null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    width = models.IntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return self.layer.identifier + ": " + self.name


class FeatureType(Resource):
    metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE, related_name="featuretype")
    parent_service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.CASCADE, related_name="featuretypes")
    is_searchable = models.BooleanField(default=False)
    default_srs = models.ForeignKey(ReferenceSystem, on_delete=models.DO_NOTHING, null=True, related_name="default_srs")
    inspire_download = models.BooleanField(default=False)
    formats = models.ManyToManyField(MimeType)
    elements = models.ManyToManyField('FeatureTypeElement')
    namespaces = models.ManyToManyField('Namespace')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.additional_srs_list = []
        self.keywords_list = []
        self.formats_list = []
        self.elements_list = []
        self.namespaces_list = []
        self.dataset_md_list = []

    def __str__(self):
        return self.metadata.identifier

    def secure_feature_type(self, is_secured: bool, groups: list, operation: RequestOperation, secured_operation: SecuredOperation):
        """ Secures the feature type or removes the secured constraints

        Args:
            is_secured (bool): Whether to secure the feature type or not
            groups (list): The list of groups which are allowed to perform an operation
            operation (RequestOperation): The operation which can be allowed
        Returns:

        """
        self.metadata.is_secured = is_secured
        if is_secured:
            sec_op = SecuredOperation()
            sec_op.operation = operation
            sec_op.save()
            for g in groups:
                sec_op.allowed_groups.add(g)
            self.metadata.secured_operations.add(sec_op)
        else:
            for sec_op in self.metadata.secured_operations.all():
                sec_op.delete()
            self.metadata.secured_operations.clear()
        self.metadata.save()
        self.save()

    def restore(self):
        """ Reset the metadata to it's original capabilities content

        Returns:
             nothing
        """
        from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
        from service.helper import service_helper
        if self.parent_service is None:
            return
        service_version = service_helper.resolve_version_enum(self.parent_service.servicetype.version)
        service = None
        if self.parent_service.servicetype.name == OGCServiceEnum.WFS.value:
            service = OGCWebFeatureServiceFactory()
            service = service.get_ogc_wfs(version=service_version, service_connect_url=self.parent_service.metadata.capabilities_original_uri)
        if service is None:
            return
        service.get_capabilities()
        service.get_single_feature_type_metadata(self.metadata.identifier)
        result = service.feature_type_list.get(self.metadata.identifier, {})
        original_ft = result.get("feature_type")
        keywords = result.get("keyword_list")

        # now restore the "metadata"
        self.title = original_ft.title
        self.abstract = original_ft.abstract
        self.metadata.keywords.clear()
        for kw in keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.metadata.keywords.add(keyword)
        self.is_custom = False


class FeatureTypeElement(Resource):
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.name


class Namespace(models.Model):
    name = models.CharField(max_length=50)
    version = models.CharField(max_length=50, blank=True, null=True)
    uri = models.CharField(max_length=500)

    def __str__(self):
        return self.name + " (" + self.uri + ")"
