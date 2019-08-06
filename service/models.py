import uuid

from django.contrib.gis.geos import Polygon
from django.db import models, transaction
from django.contrib.gis.db import models
from django.utils import timezone

from service.helper.enums import ServiceTypes
from structure.models import Group, Organization
from service.helper import xml_helper


class Keyword(models.Model):
    keyword = models.CharField(max_length=255)

    def __str__(self):
        return self.keyword


class Resource(models.Model):
    uuid = models.CharField(max_length=255, default=uuid.uuid4())
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(Group, on_delete=models.DO_NOTHING, null=True, blank=True)
    last_modified = models.DateTimeField(null=True)
    is_deleted = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        # We always want to have automatically the last timestamp from the latest change!
        self.last_modified = timezone.now()
        super().save()

    class Meta:
        abstract = True

class MetadataOrigin(models.Model):
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class MetadataRelation(models.Model):
    metadata_1 = models.ForeignKey('Metadata', on_delete=models.CASCADE, related_name="related_metadate_from")
    metadata_2 = models.ForeignKey('Metadata', on_delete=models.CASCADE, related_name="related_metadate_to")
    relation_type = models.CharField(max_length=255, null=True, blank=True)
    internal = models.BooleanField(default=False)
    origin = models.ForeignKey(MetadataOrigin, on_delete=models.CASCADE)

    def __str__(self):
        return self.metadata_1.title + " -> " + self.metadata_2.title


class Metadata(Resource):
    identifier = models.CharField(max_length=255, null=True)
    title = models.CharField(max_length=255)
    abstract = models.TextField(null=True, blank=True)
    online_resource = models.CharField(max_length=500, null=True, blank=True)
    original_uri = models.CharField(max_length=500, blank=True, null=True)

    contact = models.ForeignKey(Organization, on_delete=models.DO_NOTHING, blank=True, null=True)
    terms_of_use = models.ForeignKey('TermsOfUse', on_delete=models.DO_NOTHING, null=True)
    access_constraints = models.TextField(null=True, blank=True)
    fees = models.TextField(null=True, blank=True)

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
    # capabilities
    dimension = models.CharField(max_length=100, null=True)
    authority_url = models.CharField(max_length=255, null=True)
    metadata_url = models.CharField(max_length=255, null=True)
    # other
    keywords = models.ManyToManyField(Keyword)
    categories = models.ManyToManyField('Category')
    reference_system = models.ManyToManyField('ReferenceSystem')

    related_metadata = models.ManyToManyField(MetadataRelation)
    origin = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.keywords_list = []
        self.reference_system_list = []

    def __str__(self):
        return self.title

    def is_root(self):
        """ Checks whether the metadata describes a root service or a layer/featuretype

        Returns:
             is_root (bool): True if there is no parent service to the described service, False otherwise
        """
        is_root = False
        service = self.service
        if service is not None:
            if service.parent_service is None:
                is_root = True
        return is_root

    def _restore_layer_md(self, service, identifier: str = None):
        """ Private function for retrieving single layer metadata

        Args:
            service (OGCWebMapService): An empty OGCWebMapService object to load and parse the metadata
            identifier (str): The identifier string of the layer
        Returns:
             nothing, it changes the Metadata object itself
        """
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
            md_link = related_iso.metadata_2.metadata_url
            if md_link not in original_iso_links:
                related_iso.metadata_2.delete()
                related_iso.delete()

        # restore partially capabilities document
        if self.is_root():
            rel_md = self
        else:
            rel_md = self.service.parent_service.metadata
        cap_doc = CapabilityDocument.objects.get(related_metadata=rel_md)
        cap_doc.restore_layer(identifier)
        return

    def restore(self, identifier: str = None):
        """ Load original metadata from capabilities and ISO metadata

        Args:
            identifier (str): The identifier of a featureType or Layer (in xml often named 'name')
        Returns:
             nothing
        """
        from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
        from service.helper.ogc.wms import OGCWebMapServiceFactory
        from service.helper import service_helper
        if self.service is None:
            return
        service_version = service_helper.resolve_version_enum(self.service.servicetype.version)
        service = None
        if self.service.servicetype.name == ServiceTypes.WMS.value:
            service = OGCWebMapServiceFactory()
            service = service.get_ogc_wms(version=service_version, service_connect_url=self.original_uri)
            # check if whole service shall be restored or single layer
            if not self.is_root():
                return self._restore_layer_md(service, identifier)

        elif self.service.servicetype.name == ServiceTypes.WFS.value:
            service = OGCWebFeatureServiceFactory()
            service = service.get_ogc_wfs(version=service_version, service_connect_url=self.original_uri)
        if service is None:
            return
        service.get_capabilities()
        service.create_from_capabilities(metadata_only=True)
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

        cap_doc = CapabilityDocument.objects.get(related_metadata=self)
        cap_doc.restore()

    def get_related_metadata_uris(self):
        """ Generates a list of all related metadata online links and returns them

        Returns:
             links (list): A list containing all online links of related metadata
        """
        rel_mds = self.related_metadata.all()
        links = []
        for md in rel_mds:
            links.append(md.metadata_2.metadata_url)
        return links



class CapabilityDocument(Resource):
    related_metadata = models.OneToOneField(Metadata, on_delete=models.CASCADE)
    original_capability_document = models.TextField()
    current_capability_document = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.related_metadata

    def restore(self):
        """ We overwrite the current metadata xml with the original

        Returns:
             nothing
        """
        self.current_capability_document = self.original_capability_document
        self.save()

    def restore_layer(self, identifier: str):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.root_layer = None
        self.feature_type_list = []
        self.formats_list = []
        self.categories_list = []

    def __str__(self):
        return str(self.id)

    @transaction.atomic
    def delete_layer_data(self, layer):
        """ Delete all layer data like related iso metadata

        Args:
            layer (Layer): The current layer object
        Returns:
            nothing
        """
        # remove related metadata
        iso_mds = MetadataRelation.objects.filter(metadata_1=layer.metadata)
        for iso_md in iso_mds:
            md_2 = iso_md.metadata_2
            md_2.delete()
            iso_md.delete()
        layer.delete()

    @transaction.atomic
    def delete(self, using=None, keep_parents=False):
        """ Overwrites default delete method

        Recursively remove layer children

        :param using:
        :param keep_parents:
        :return:
        """
        layers = self.child_service.all()
        for layer in layers:
            self.delete_layer_data(layer)
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


class Layer(Service):
    identifier = models.CharField(max_length=500, null=True)
    hits = models.IntegerField(default=0)
    preview_image = models.CharField(max_length=100)
    preview_extend = models.CharField(max_length=100)
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
    action = models.CharField(max_length=255, null=True)
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
    identifier = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    abstract = models.TextField(null=True)
    is_custom = models.BooleanField(default=False)
    searchable = models.BooleanField(default=False)
    default_srs = models.ForeignKey(ReferenceSystem, on_delete=models.DO_NOTHING, null=True, related_name="default_srs")
    additional_srs = models.ManyToManyField(ReferenceSystem)
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
    keywords = models.ManyToManyField(Keyword)
    formats = models.ManyToManyField(MimeType)
    elements = models.ManyToManyField('FeatureTypeElement')
    namespaces = models.ManyToManyField('Namespace')
    service = models.ForeignKey(Service, null=True,  blank=True, on_delete=models.CASCADE, related_name="featuretypes")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # non persisting attributes
        self.additional_srs_list = []
        self.keywords_list = []
        self.formats_list = []
        self.elements_list = []
        self.namespaces_list = []

    def __str__(self):
        return self.identifier

    def restore(self):
        from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
        from service.helper import service_helper
        if self.service is None:
            return
        service_version = service_helper.resolve_version_enum(self.service.servicetype.version)
        service = None
        if self.service.servicetype.name == ServiceTypes.WFS.value:
            service = OGCWebFeatureServiceFactory()
            service = service.get_ogc_wfs(version=service_version, service_connect_url=self.service.metadata.original_uri)
        if service is None:
            return
        service.get_capabilities()
        service.get_single_feature_type_metadata(self.identifier)
        result = service.feature_type_list.get(self.identifier, {})
        original_ft = result.get("feature_type")
        keywords = result.get("keyword_list")

        # now restore the "metadata"
        self.title = original_ft.title
        self.abstract = original_ft.abstract
        self.keywords.clear()
        for kw in keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            self.keywords.add(keyword)
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
