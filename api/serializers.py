"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.08.19

"""
from collections import OrderedDict, Iterable

from django.db.models import QuerySet
from django.http import HttpRequest
from django.urls import reverse
from rest_framework import serializers

from MrMap.settings import ROOT_URL
from api.settings import API_EXCLUDE_METADATA_RELATIONS
from service.forms import RegisterNewResourceWizardPage2
from service.helper import service_helper
from service.models import ServiceType, Metadata, Category, Dimension
from service.settings import DEFAULT_SERVICE_BOUNDING_BOX_EMPTY
from structure.models import MrMapGroup, Role, Permission
from monitoring.models import Monitoring
from users.helper import user_helper


class ServiceTypeSerializer(serializers.ModelSerializer):
    """ Serializer for ServiceType model

    """
    class Meta:
        model = ServiceType
        fields = [
            "name",
            "version"
        ]

        # improves performance by 300%!
        # check out https://hakibenita.com/django-rest-framework-slow for more information
        read_only_fields = fields


class OrganizationSerializer(serializers.Serializer):
    """ Serializer for Organization model

    """
    id = serializers.IntegerField()
    organization_name = serializers.CharField()
    is_auto_generated = serializers.BooleanField()
    person_name = serializers.CharField()
    email = serializers.EmailField()
    phone = serializers.CharField()
    facsimile = serializers.CharField()
    city = serializers.CharField()
    country = serializers.CharField()


class GroupSerializer(serializers.ModelSerializer):
    """ Serializer for Organization model

    """
    class Meta:
        model = MrMapGroup
        fields = [
            "id",
            "name",
            "description",
            "organization",
            "role",
            "publish_for_organizations",
        ]

        # improves performance by 300%!
        # check out https://hakibenita.com/django-rest-framework-slow for more information
        read_only_fields = fields


class PermissionSerializer(serializers.ModelSerializer):
    """ Serializer for Organization model

    """
    class Meta:
        model = Permission
        fields = [
            p.name for p in Permission._meta.fields
        ]

        # improves performance by 300%!
        # check out https://hakibenita.com/django-rest-framework-slow for more information
        read_only_fields = fields


class RoleSerializer(serializers.ModelSerializer):
    """ Serializer for Organization model

    """
    permission = PermissionSerializer()

    class Meta:
        model = Role
        fields = [
            "id",
            "name",
            "description",
            "permission",
        ]

        # improves performance by 300%!
        # check out https://hakibenita.com/django-rest-framework-slow for more information
        read_only_fields = fields


class PendingTaskSerializer(serializers.Serializer):
    """ Serializer for PendingTask model

    """
    description = serializers.CharField()
    progress = serializers.FloatField()
    is_finished = serializers.BooleanField()


class MetadataRelationMetadataSerializer(serializers.Serializer):
    """ Serializer for Metadata records inside MetadataRelation model

    """
    id = serializers.IntegerField(read_only=True)
    type = serializers.CharField(read_only=True, source="metadata_type")

    class Meta:
        model = Metadata

class MetadataRelationSerializer(serializers.Serializer):
    """ Serializer for MetadataRelation model

    """
    relation_type = serializers.CharField(read_only=True)
    relation_to = MetadataRelationMetadataSerializer(source="metadata_to")


class MetadataSerializer(serializers.Serializer):
    """ Serializer for Metadata model

    """
    id = serializers.UUIDField()
    easy_id = serializers.CharField(source="public_id")
    metadata_type = serializers.CharField()
    identifier = serializers.CharField()
    title = serializers.CharField()
    abstract = serializers.CharField()
    online_resource = serializers.CharField()

    service_metadata_original_uri = serializers.CharField()
    capabilities_uri = serializers.CharField()
    metadata_url = serializers.CharField()
    service = serializers.PrimaryKeyRelatedField(read_only=True)
    organization = serializers.PrimaryKeyRelatedField(read_only=True, source="contact")
    related_metadata = MetadataRelationSerializer(many=True)
    keywords = serializers.StringRelatedField(read_only=True, many=True)


class ServiceSerializer(serializers.Serializer):
    """ Serializer for Service model

    """
    id = serializers.UUIDField()
    published_for = serializers.PrimaryKeyRelatedField(read_only=True)
    metadata = serializers.PrimaryKeyRelatedField(read_only=True)
    is_root = serializers.BooleanField()
    service_type = ServiceTypeSerializer()

    def create(self, validated_data, request: HttpRequest = None):
        """ Creates a new service

        Starts the regular registration process

        Args:
            validated_data (dict): The validated data from a POST request
        Returns:
             pending_task (PendingTask) or None
        """
        # Writing of .get("xy", None) or None makes sure that empty strings will be mapped to None
        user = user_helper.get_user(request=request)
        get_capabilities_uri = validated_data.get("uri", None) or None
        registering_with_group = validated_data.get("group", None) or None
        registering_for_org = validated_data.get("for-org", None) or None
        has_ext_auth = validated_data.get("ext-auth", False) or False
        ext_auth_username = validated_data.get("ext-username", None) or None
        ext_auth_password = validated_data.get("ext-password", None) or None
        ext_auth_type = validated_data.get("ext-auth-type", None) or None

        # Split uri in components as it is done with RegisterNewServiceWizardPage1
        url_dict = service_helper.split_service_uri(get_capabilities_uri)
        ogc_request = url_dict["request"]
        ogc_service = url_dict["service"].value
        ogc_version = url_dict["version"]
        uri = url_dict["base_uri"]

        init_data = {
            "ogc_request": ogc_request,
            "ogc_service": ogc_service,
            "ogc_version": ogc_version,
            "uri": uri,
            "registering_with_group": registering_with_group,
            "registering_for_other_organization": registering_for_org,
            "service_needs_authentication": has_ext_auth,
            "username": ext_auth_username,
            "password": ext_auth_password,
            "authentication_type": ext_auth_type,
        }

        # Use RegisterNewResourceWizardPage2 workflow as for frontend registration
        form = RegisterNewResourceWizardPage2(
            data=init_data,
            request=request
        )
        if form.is_valid():
            pending_task = service_helper.create_new_service(form, user)
            return pending_task
        return None


class LayerSerializer(ServiceSerializer):
    """ Serializer for Layer model

    """
    id = serializers.UUIDField()
    identifier = serializers.CharField()
    preview_image = serializers.CharField()
    preview_extent = serializers.CharField()
    is_available = serializers.BooleanField()
    is_active = serializers.BooleanField()
    parent_service = serializers.PrimaryKeyRelatedField(read_only=True)
    child_layers = serializers.PrimaryKeyRelatedField(read_only=True, many=True)
    service_type = ServiceTypeSerializer()


class CategorySerializer(serializers.ModelSerializer):
    """ Serializer for Category model

    """
    metadata_count = serializers.IntegerField(read_only=True, )

    class Meta:
        model = Category
        fields = [
            "id",
            "type",
            "title_EN",
            "description_EN",
            "title_locale_1",
            "description_locale_1",
            "title_locale_2",
            "description_locale_2",
            "symbol",
            "online_link",
            "metadata_count",
        ]
        read_only_fields = fields


class DimensionSerializer(serializers.ModelSerializer):
    """ Serializer for Dimension model

    """
    class Meta:
        model = Dimension
        fields = [
            "type",
            "custom_name",
            "units",
            "extent",
        ]
        read_only_fields = fields


class CatalogueMetadataSerializer(serializers.Serializer):
    """ Serializer for Metadata model

    """
    id = serializers.IntegerField(read_only=True)
    identifier = serializers.CharField(read_only=True)
    metadata_type = serializers.CharField(read_only=True, label="type")
    title = serializers.CharField(read_only=True)
    abstract = serializers.CharField(read_only=True)
    spatial_extent_geojson = serializers.CharField(read_only=True, source="bounding_geometry.geojson")
    capabilities_uri = serializers.CharField(read_only=True)
    xml_metadata_uri = serializers.CharField(read_only=True, source="service_metadata_uri")
    html_metadata_uri = serializers.CharField(read_only=True)
    fees = serializers.CharField(read_only=True)
    access_constraints = serializers.CharField(read_only=True)
    licence = serializers.PrimaryKeyRelatedField(read_only=True)
    parent_service = serializers.IntegerField(read_only=True, source="service.parent_service.metadata.id")
    organization = OrganizationSerializer(read_only=True, source="contact")
    related_metadata = MetadataRelationSerializer(read_only=True, many=True)
    keywords = serializers.StringRelatedField(read_only=True, many=True)
    categories = CategorySerializer(read_only=True, many=True)
    dimensions = DimensionSerializer(read_only=True, many=True)

    class Meta:
        model = Metadata


class MonitoringSerializer(serializers.ModelSerializer):
    """ Serializer for Monitoring model

    """
    class Meta:
        model = Monitoring
        fields = [
            'id', 'metadata', 'timestamp', 'duration', 'status_code', 'error_msg', 'available', 'monitored_uri',
            'monitoring_run'
        ]

        # improves performance by 300%!
        # check out https://hakibenita.com/django-rest-framework-slow for more information
        read_only_fields = fields


class MonitoringSummarySerializer(serializers.Serializer):
    """ Serializer for Monitoring summary

    """
    last_monitoring = MonitoringSerializer()
    avg_response_time = serializers.DurationField()
    avg_availability_percent = serializers.FloatField()


def serialize_metadata_relation(md: Metadata) -> list:
    """ Serializes the related_metadata of a metadata element into a list of dict elements

    Faster version than using ModelSerializers

    Args:
        md (Metadata): The metadata element
    Returns:
         data_list (list): The list containing serialized dict elements
    """
    relations = []
    md_relations = md.related_metadata.all()

    # Exclude harvested relations for a csw. It would be way too much without giving useful information
    if md.is_catalogue_metadata:
        md_relations = md_relations.exclude(
            **API_EXCLUDE_METADATA_RELATIONS
        )

    for rel in md_relations:
        md_to = rel.metadata_to

        rel_obj = OrderedDict()
        rel_obj["relation_type"] = rel.relation_type
        rel_obj["metadata"] = {
            "id": md_to.id,
            "type": md_to.metadata_type,
        }

        relations.append(rel_obj)

    return relations


def serialize_contact(md: Metadata) -> OrderedDict:
    """ Serializes the contact of a metadata element into a dict element

    Faster version than using ModelSerializers

    Args:
        md (Metadata): The metadata element
    Returns:
         data_list (list): The list containing serialized dict elements
    """
    contact = OrderedDict()
    md_contact = md.contact

    if md_contact is None:
        return None

    contact["id"] = md_contact.id
    contact["organization_name"] = md_contact.organization_name
    contact["is_auto_generated"] = md_contact.is_auto_generated
    contact["person_name"] = md_contact.person_name
    contact["email"] = md_contact.email
    contact["phone"] = md_contact.phone
    contact["facsimile"] = md_contact.facsimile
    contact["city"] = md_contact.city
    contact["country"] = md_contact.country

    return contact


def serialize_dimensions(md: Metadata) -> list:
    """ Serializes the dimensions of a metadata element into a list of dict elements

    Faster version than using ModelSerializers

    Args:
        md (Metadata): The metadata element
    Returns:
         data_list (list): The list containing serialized dict elements
    """
    dimensions = []

    for dim in md.dimensions.all():
        dimension = OrderedDict()

        dimension["type"] = dim.type
        dimension["custom_name"] = dim.custom_name
        dimension["units"] = dim.units
        dimension["extent"] = dim.extent

        dimensions.append(dimension)

    return dimensions


def serialize_licence(md: Metadata) -> OrderedDict:
    """ Serializes the licence of a metadata element into a dict element

    Args:
        md (Metadata): The metadata element
    Returns:
         licence (OrderedDict): The serialized licence elements
    """
    licence = OrderedDict()
    if md.licence is None:
        return licence
    licence["name"] = md.licence.name
    licence["identifier"] = md.licence.identifier
    licence["description"] = md.licence.description
    licence["url"] = md.licence.description_url
    licence["symbol_url"] = md.licence.symbol_url
    licence["is_open_data"] = md.licence.is_open_data
    return licence


def serialize_categories(md: Metadata) -> list:
    """ Serializes the categories of a metadata element into a list of dict elements

    Faster version than using ModelSerializers

    Args:
        md (Metadata): The metadata element
    Returns:
         data_list (list): The list containing serialized dict elements
    """
    categories = []
    all_cat = md.categories.all()
    for cat in all_cat:
        category = OrderedDict()

        category["id"] = cat.id
        category["type"] = cat.type
        category["title_EN"] = cat.title_EN
        category["description_EN"] = cat.description_EN
        category["title_locale_1"] = cat.title_locale_1
        category["description_locale_1"] = cat.description_locale_1
        category["title_locale_2"] = cat.title_locale_2
        category["description_locale_2"] = cat.description_locale_2
        category["symbol"] = cat.symbol
        category["online_link"] = cat.online_link

        categories.append(category)

    return categories


def perform_catalogue_entry_serialization(md: Metadata) -> OrderedDict:
    """ Performs serialization for a single metadata object

    Args:
        md (Metadata): The metadata object
    Returns:
        serialized (OrderedDict): A dict object, containing the metadata catalogue data
    """
    # fetch keywords beforehand
    keywords = md.keywords.all()
    additional_urls = md.additional_urls.all()

    # fetch bounding geometry beforehand
    bounding_geometry = md.bounding_geometry
    if bounding_geometry is None:
        bounding_geometry = DEFAULT_SERVICE_BOUNDING_BOX_EMPTY

    try:
        if md.is_featuretype_metadata:
            parent_service = md.featuretype.parent_service.id
        else:
            parent_service = md.service.parent_service.metadata.id
    except Exception:
        parent_service = None

    can_have_preview = md.is_service_metadata or md.is_featuretype_metadata or md.is_layer_metadata

    # Create response data
    serialized = OrderedDict()
    serialized["id"] = md.id
    serialized["easy_id"] = md.public_id
    serialized["file_identifier"] = md.identifier
    serialized["type"] = md.metadata_type
    serialized["title"] = md.title
    serialized["abstract"] = md.abstract
    serialized["spatial_extent_geojson"] = bounding_geometry.geojson
    serialized["online_resource_uri"] = md.online_resource
    serialized["capabilities_uri"] = md.capabilities_uri
    serialized["xml_metadata_uri"] = md.service_metadata_uri
    serialized["html_metadata_uri"] = md.html_metadata_uri
    serialized["additional_uris"] = [{uri.url: uri.description} for uri in additional_urls]
    serialized["preview_uri"] = "{}{}".format(ROOT_URL, reverse("resource:get-service-metadata-preview", args=(str(md.id),))) if can_have_preview else None
    serialized["fees"] = md.fees
    serialized["access_constraints"] = md.access_constraints
    serialized["licence"] = serialize_licence(md)
    serialized["parent_service"] = parent_service
    serialized["keywords"] = [kw.keyword for kw in keywords]
    serialized["organization"] = serialize_contact(md)
    serialized["related_metadata"] = serialize_metadata_relation(md)
    serialized["categories"] = serialize_categories(md)
    serialized["dimensions"] = serialize_dimensions(md)

    return serialized


def serialize_catalogue_metadata(md_queryset: QuerySet) -> list:
    """ Serializes a metadata QuerySet into a list of dict elements

    Faster version than using ModelSerializers

    Args:
        md_queryset (QuerySet): The queryset containing the metadata elements
    Returns:
         data_list (list): The list containing serialized dict elements
    """
    # If no queryset but a single metadata is provided, we do not add everything into a
    is_single_retrieve = not isinstance(md_queryset, Iterable)

    if is_single_retrieve:
        ret_val = perform_catalogue_entry_serialization(md_queryset)
    else:
        ret_val = [perform_catalogue_entry_serialization(md) for md in md_queryset]

    return ret_val
