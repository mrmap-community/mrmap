"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.08.19

"""
from rest_framework import serializers

from service.forms import RegisterNewServiceWizardPage2
from service.helper import service_helper
from service.models import ServiceType, Metadata, Category, Dimension
from structure.models import MrMapGroup, Role, Permission


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
    type = serializers.CharField(read_only=True, source="metadata_type.type")
    identifier = serializers.CharField(read_only=True)

    class Meta:
        model = Metadata

class MetadataRelationSerializer(serializers.Serializer):
    """ Serializer for MetadataRelation model

    """
    relation_from = MetadataRelationMetadataSerializer(source="metadata_from")
    relation_type = serializers.CharField(read_only=True)
    relation_to = MetadataRelationMetadataSerializer(source="metadata_to")


class MetadataSerializer(serializers.Serializer):
    """ Serializer for Metadata model

    """
    id = serializers.IntegerField()
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
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    published_for = serializers.PrimaryKeyRelatedField(read_only=True)
    metadata = serializers.PrimaryKeyRelatedField(read_only=True)
    is_root = serializers.BooleanField()
    servicetype = ServiceTypeSerializer()

    def create(self, validated_data):
        """ Creates a new service

        Starts the regular registration process

        Args:
            validated_data (dict): The validated data from a POST request
        Returns:
             pending_task (PendingTask) or None
        """
        # Writing of .get("xy", None) or None makes sure that empty strings will be mapped to None
        user = validated_data.get("user", None)
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

        # Use RegisterNewServiceWizardPage2 workflow as for frontend registration
        form = RegisterNewServiceWizardPage2(
            init_data,
            user=user
        )
        if form.is_valid():
            pending_task = service_helper.create_new_service(form, user)
            return pending_task
        return None


class LayerSerializer(ServiceSerializer):
    """ Serializer for Layer model

    """
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    identifier = serializers.CharField()
    preview_image = serializers.CharField()
    preview_extent = serializers.CharField()
    is_available = serializers.BooleanField()
    is_active = serializers.BooleanField()
    parent_service = serializers.PrimaryKeyRelatedField(read_only=True)
    child_layers = serializers.PrimaryKeyRelatedField(read_only=True, many=True)
    servicetype = ServiceTypeSerializer()


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
    terms_of_use = serializers.PrimaryKeyRelatedField(read_only=True)
    parent_service = serializers.IntegerField(read_only=True, source="service.parent_service.metadata.id")
    organization = OrganizationSerializer(read_only=True, source="contact")
    related_metadata = MetadataRelationSerializer(read_only=True, many=True)
    keywords = serializers.StringRelatedField(read_only=True, many=True)
    categories = CategorySerializer(read_only=True, many=True)
    dimensions = DimensionSerializer(read_only=True, many=True)

    class Meta:
        model = Metadata


