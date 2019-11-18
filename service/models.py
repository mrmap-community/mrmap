import uuid

from django.contrib.gis.geos import Polygon
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.contrib.gis.db import models
from django.utils import timezone

from MapSkinner.settings import HTTP_OR_SSL, HOST_NAME, GENERIC_NAMESPACE_TEMPLATE
from service.helper.enums import ServiceEnum, VersionEnum, MetadataEnum
from structure.models import Group, Organization
from service.helper import xml_helper


class Keyword(models.Model):
    keyword = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.keyword


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


class RequestOperation(models.Model):
    operation_name = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return self.operation_name


class SecuredOperation(models.Model):
    operation = models.ForeignKey(RequestOperation, on_delete=models.CASCADE, null=True, blank=True)
    allowed_groups = models.ManyToManyField(Group, related_name="allowed_operations")
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
        # delete current object
        super().delete(using, keep_parents)

        md_type = md.metadata_type.type

        # continue with possibly existing children
        if md_type == MetadataEnum.SERVICE.value or md_type == MetadataEnum.LAYER.value:
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
            for child_layer in layer.child_layer.all():
                sec_ops = SecuredOperation.objects.filter(
                    secured_metadata=child_layer.metadata,
                    operation=operation
                )
                for sec_op in sec_ops:
                    sec_op.delete()


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
    inherit_proxy_uris = models.BooleanField(default=False)
    spatial_res_type = models.CharField(max_length=100, null=True)
    spatial_res_value = models.CharField(max_length=100, null=True)
    is_broken = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
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
        service_version = self.service.servicetype.version
        for v in VersionEnum:
            if v.value == service_version:
                return v
        return service_version

    def find_max_bounding_box(self):
        """ Returns the largest bounding box of all children

        Saves the found bounding box to bounding_geometry for faster access

        Returns:

        """
        children = self.service.child_service.all()
        max_box = None
        for child in children:
            bbox = child.layer.bbox_lat_lon
            if max_box is None:
                max_box = bbox
            else:
                ba = bbox.area
                ma = max_box.area
                if ba > ma:
                    max_box = bbox
        self.bounding_geometry = max_box
        self.save()
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
            keyword = service_helper.keyword_get_or_create_safely(kw)
            #keyword = Keyword.objects.get_or_create(keyword=kw)[0]
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

    def _restore_feature_type_md(self, service, identifier: str = None):
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
        f_t = service.get_feature_type_by_identifier(identifier)
        f_t_obj = f_t.get("feature_type", None)
        f_t_iso_links = f_t.get("dataset_md_list", [])
        self.title = f_t_obj.metadata.title
        self.abstract = f_t_obj.metadata.abstract
        self.is_custom = False
        self.keywords.clear()
        for kw in f_t_obj.metadata.keywords_list:
            keyword = service_helper.keyword_get_or_create_safely(kw)
            #keyword = Keyword.objects.get_or_create(keyword=kw)[0]
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
            rel_md = self.featuretype.service.metadata
        cap_doc = Document.objects.get(related_metadata=rel_md)
        cap_doc.restore_subelement(identifier)
        return

    def _restore_wms(self, identifier: str = None):
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
        service.create_from_capabilities(metadata_only=True)

        # check if whole service shall be restored or single layer
        if not self.is_root():
            return self._restore_layer_md(service, identifier)

        self.title = service.service_identification_title
        self.abstract = service.service_identification_abstract
        self.access_constraints = service.service_identification_accessconstraints
        keywords = service.service_identification_keywords
        self.keywords.clear()
        for kw in keywords:
            keyword = service_helper.keyword_get_or_create_safely(kw)
            #keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        # by default no categories
        self.categories.clear()
        self.is_custom = False
        self.inherit_proxy_uris = False

        cap_doc = Document.objects.get(related_metadata=self)
        cap_doc.restore()

    def _restore_wfs(self, identifier: str = None):
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
            return self._restore_feature_type_md(service_tmp, identifier)

        self.title = service_tmp.service_identification_title
        self.abstract = service_tmp.service_identification_abstract
        self.access_constraints = service_tmp.service_identification_accessconstraints
        keywords = service_tmp.service_identification_keywords
        self.keywords.clear()
        for kw in keywords:
            keyword = service_helper.keyword_get_or_create_safely(kw)
            #keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)

        # by default no categories
        self.categories.clear()
        self.is_custom = False
        self.inherit_proxy_uris = False

        cap_doc = Document.objects.get(related_metadata=service.metadata)
        cap_doc.restore()

    def restore(self, identifier: str = None):
        """ Load original metadata from capabilities and ISO metadata

        Args:
            identifier (str): The identifier of a featureType or Layer (in xml often named 'name')
        Returns:
             nothing
        """

        # identify whether this is a wfs or wms (we need to handle them in different ways)
        service_type = self.get_service_type()
        if service_type == ServiceEnum.WFS.value:
            self._restore_wfs(identifier)
        elif service_type == ServiceEnum.WMS.value:
            self._restore_wms(identifier)

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

    def _set_document_operations_secured(self, is_secured: bool):
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
            cap_doc.set_operations_secured(is_secured)
        except ObjectDoesNotExist:
            pass

    def set_secured(self, is_secured: bool):
        """ Set is_secured to a new value.

        Iterates over all children for the same purpose.

        Args:
            is_secured (bool): The new value for is_secured
        Returns:

        """
        self.is_secured = is_secured
        self._set_document_operations_secured(is_secured)

        md_type = self.metadata_type.type

        children = []
        if md_type == MetadataEnum.SERVICE.value or md_type == MetadataEnum.LAYER.value:
            if self.service.servicetype.name == ServiceEnum.WMS.value:
                parent_service = self.service
                children = Metadata.objects.filter(
                    service__parent_service=parent_service
                )
                for child in children:
                    child._set_document_operations_secured(is_secured)

            elif self.service.servicetype.name == ServiceEnum.WFS.value:
                children = [ft.metadata for ft in self.service.featuretypes.all()]

            for child in children:
                child.is_secured = is_secured
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
            "GetMap": service.get_map_uri,
            "GetFeatureInfo": service.get_feature_info_uri,
            "DescribeLayer": service.describe_layer_uri,
            "GetLegendGraphic": service.get_legend_graphic_uri,
            "GetStyles": service.get_styles_uri,
        }
        for op in request_objs:
            # skip GetCapabilities - it is already set to another internal link
            if "GetCapabilities" in op.tag:
                continue
            if not is_secured:
                uri = op_uri_dict.get(op.tag, "")
            res_objs = xml_helper.try_get_element_from_xml(
                ".//" + GENERIC_NAMESPACE_TEMPLATE.format("OnlineResource")
                , op
            )
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
        service = self.related_metadata.service
        op_uri_dict = {
            "DescribeFeatureType": service.describe_layer_uri,
            "GetFeature": service.get_feature_info_uri,
            "GetPropertyValue": None,
            "ListStoredQueries": None,
            "DescribeStoredQueries": None,
        }
        for op in operation_objs:
            # skip GetCapabilities - it is already set to another internal link
            name = op.tag
            if name == "GetCapabilities":
                continue
            if not is_secured:
                uri = op_uri_dict.get(name, "")
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
        service = self.related_metadata.service
        op_uri_dict = {
            "DescribeFeatureType": service.describe_layer_uri,
            "GetFeature": service.get_feature_info_uri,
            "GetPropertyValue": "",
            "ListStoredQueries": "",
            "DescribeStoredQueries": "",
        }
        for op in operation_objs:
            # skip GetCapabilities - it is already set to another internal link
            name = xml_helper.try_get_attribute_from_xml_element(op, "name")
            if name == "GetCapabilities":
                continue
            if not is_secured:
                uri = op_uri_dict.get(name, "")
            http_objs = xml_helper.try_get_element_from_xml(".//" + GENERIC_NAMESPACE_TEMPLATE.format("HTTP"), op)
            for http_obj in http_objs:
                requ_objs = http_obj.getchildren()
                for requ_obj in requ_objs:
                    xml_helper.write_attribute(
                        requ_obj,
                        attrib="{http://www.w3.org/1999/xlink}href",
                        txt=uri
                    )

    def set_operations_secured(self, is_secured: bool):
        """ Change external links to internal for service operations

        Args:
            is_secured (bool): Whether the service is secured or not
        Returns:

        """
        xml_obj = xml_helper.parse_xml(self.current_capability_document)
        if is_secured:
            uri = "{}{}/service/metadata/proxy/operation/{}?".format(HTTP_OR_SSL, HOST_NAME, self.related_metadata.id)
        else:
            uri = ""
        _type = self.related_metadata.service.servicetype.name
        _version = self.related_metadata.get_service_version()
        if _type == ServiceEnum.WMS.value:
            self._set_wms_operations_secured(xml_obj, uri, is_secured)
        elif _type == ServiceEnum.WFS.value:
            if _version is VersionEnum.V_1_0_0:
                self._set_wfs_1_0_0_operations_secured(xml_obj, uri, is_secured)
            else:
                self._set_wfs_operations_secured(xml_obj, uri, is_secured)

        self.current_capability_document = xml_helper.xml_to_string(xml_obj)
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
    get_capabilities_uri = models.CharField(max_length=1000, null=True, blank=True)
    get_map_uri = models.CharField(max_length=1000, null=True, blank=True)
    get_feature_info_uri = models.CharField(max_length=1000, null=True, blank=True)
    describe_layer_uri = models.CharField(max_length=1000, null=True, blank=True)
    get_legend_graphic_uri = models.CharField(max_length=1000, null=True, blank=True)
    get_styles_uri = models.CharField(max_length=1000, null=True, blank=True)
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

    def perform_single_element_securing(self, element, is_secured: bool, groups: list, operation: RequestOperation):
        """ Secures a single element

        Args:
            element: The element which shall be secured
            is_secured (bool): Whether to secure the element or not
            groups (list): A list of groups which are allowed to perform an operation
            operation (RequestOperation): The operation which can be performed by the groups
        Returns:

        """
        element.metadata.is_secured = is_secured
        if is_secured:
            sec_op = SecuredOperation()
            sec_op.operation = operation
            sec_op.save()
            for g in groups:
                sec_op.allowed_groups.add(g)
            element.metadata.secured_operations.add(sec_op)
        else:
            for sec_op in element.metadata.secured_operations.all():
                sec_op.delete()
            element.metadata.secured_operations.clear()
        element.metadata.save()
        element.save()

    def _recursive_secure_sub_layers(self, current, is_secured: bool, groups: list, operation: RequestOperation):
        """ Recursive implementation of securing all sub layers of a current layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            groups (list): The list of groups which are allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
        Returns:
             nothing
        """
        self.perform_single_element_securing(current, is_secured, groups, operation)

        for layer in current.child_layer.all():
            self._recursive_secure_sub_layers(layer, is_secured, groups, operation)

    def _secure_sub_layers(self, is_secured: bool, groups: list, operation: RequestOperation):
        """ Secures all sub layers of this layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            groups (list): The list of groups which are allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
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
        self._recursive_secure_sub_layers(start_element, is_secured, groups, operation)

    def _secure_feature_types(self, is_secured: bool, groups: list, operation: RequestOperation):
        """ Secures all sub layers of this layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            groups (list): The list of groups which are allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
        Returns:
             nothing
        """
        if self.is_root:
            elements = self.featuretypes.all()
            for element in elements:
                self.perform_single_element_securing(element, is_secured, groups, operation)

    def secure_sub_elements(self, is_secured: bool, groups: list, operation: RequestOperation):
        """ Secures all sub elements of this layer

        Args:
            is_secured (bool): Whether the sublayers shall be secured or not
            groups (list): The list of groups which are allowed to run the operation
            operation (RequestOperation): The operation that is allowed to be run
        Returns:
             nothing
        """
        if self.servicetype.name == ServiceEnum.WMS.value:
            self._secure_sub_layers(is_secured, groups, operation)
        elif self.servicetype.name == ServiceEnum.WFS.value:
            self._secure_feature_types(is_secured, groups, operation)

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

        # change some external linkage to internal links for the current_capability_document
        uri = "{}{}/service/capabilities/{}".format(HTTP_OR_SSL, HOST_NAME, self.metadata.id)
        xml = xml_helper.parse_xml(xml)

        # wms and wfs have to be handled differently!
        # Furthermore each standard has a different handling of attributes and elements ...
        if self.servicetype.name == ServiceEnum.WMS.value:
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
        elif self.servicetype.name == ServiceEnum.WFS.value:
            if self.servicetype.version == "1.0.0":
                prefix = "wfs:"
                xml_helper.write_text_to_element(xml, "//{}Service/{}OnlineResource".format(prefix, prefix), uri)
                xml_helper.write_attribute(xml, "//{}GetCapabilities/{}DCPType/{}HTTP/{}Get".format(prefix, prefix, prefix, prefix),
                                           "onlineResource", uri)
                xml_helper.write_attribute(xml, "//{}GetCapabilities/{}DCPType/{}HTTP/{}Post".format(prefix, prefix, prefix, prefix),
                                           "onlineResource", uri)
            else:
                prefix = "ows:"
                xml_helper.write_attribute(xml, "//{}ContactInfo/{}OnlineResource".format(prefix, prefix),
                                           "{http://www.w3.org/1999/xlink}href", uri)
                xml_helper.write_attribute(xml, "//{}Operation[@name='GetCapabilities']/{}DCP/{}HTTP/{}Get".format(prefix, prefix, prefix, prefix),
                                           "{http://www.w3.org/1999/xlink}href", uri)
                xml_helper.write_attribute(xml, "//{}Operation[@name='GetCapabilities']/{}DCP/{}HTTP/{}Post".format(prefix, prefix, prefix, prefix),
                                           "{http://www.w3.org/1999/xlink}href", uri)

        xml = xml_helper.xml_to_string(xml)

        cap_doc.current_capability_document = xml
        cap_doc.related_metadata = self.metadata
        cap_doc.save()


class Layer(Service):
    class Meta:
        ordering = ["position"]
    identifier = models.CharField(max_length=500, null=True)
    hits = models.IntegerField(default=0)
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

    def __str__(self):
        return str(self.identifier)

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
    layer = models.ForeignKey(Layer, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    uri = models.CharField(max_length=500)
    height = models.IntegerField()
    width = models.IntegerField()
    mime_type = models.CharField(max_length=500)

    def __str__(self):
        return self.layer.name + ": " + self.name


class FeatureType(Resource):
    metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE, related_name="featuretype")
    service = models.ForeignKey(Service, null=True,  blank=True, on_delete=models.CASCADE, related_name="featuretypes")
    is_searchable = models.BooleanField(default=False)
    default_srs = models.ForeignKey(ReferenceSystem, on_delete=models.DO_NOTHING, null=True, related_name="default_srs")
    inspire_download = models.BooleanField(default=False)
    bbox_lat_lon = models.PolygonField(default=Polygon(
        (
            (-90.0, -180.0),
            (-90.0, 180.0),
            (90.0, 180.0),
            (90.0, -180.0),
            (-90.0, -180.0),
        )
    ))
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

    def secure_feature_type(self, is_secured: bool, groups: list, operation: RequestOperation):
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
        if self.service is None:
            return
        service_version = service_helper.resolve_version_enum(self.service.servicetype.version)
        service = None
        if self.service.servicetype.name == ServiceEnum.WFS.value:
            service = OGCWebFeatureServiceFactory()
            service = service.get_ogc_wfs(version=service_version, service_connect_url=self.service.metadata.capabilities_original_uri)
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
            keyword = service_helper.keyword_get_or_create_safely(kw)
            #keyword = Keyword.objects.get_or_create(keyword=kw)[0]
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
