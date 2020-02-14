"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.08.19

"""
from rest_framework import serializers

from service.models import ServiceType
from structure.models import Group, Role, Permission
from monitoring.models import Monitoring


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
        model = Group
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


class KeywordSerializer(serializers.Serializer):
    """ Serializer for Keyword model

    """
    keyword = serializers.CharField(read_only=True)


class MetadataRelationSerializer(serializers.Serializer):
    """ Serializer for MetadataRelation model

    """
    id = serializers.PrimaryKeyRelatedField(read_only=True, source="metadata_to")


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
    keywords = KeywordSerializer(read_only=True, many=True)
    #contact = OrganizationSerializer()


class ServiceSerializer(serializers.Serializer):
    """ Serializer for Service model

    """
    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    published_for = serializers.PrimaryKeyRelatedField(read_only=True)
    metadata = serializers.PrimaryKeyRelatedField(read_only=True)
    is_root = serializers.BooleanField()
    servicetype = ServiceTypeSerializer()


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
    child_layer = serializers.PrimaryKeyRelatedField(read_only=True, many=True)
    servicetype = ServiceTypeSerializer()


class CatalogueMetadataSerializer(serializers.Serializer):
    """ Serializer for Metadata model

    """
    id = serializers.IntegerField()
    identifier = serializers.CharField()
    title = serializers.CharField()
    abstract = serializers.CharField()
    bounding_geometry = serializers.CharField()  # ToDo: Use gis module to serialize the models.PolygonField()
    #online_resource = serializers.CharField()
    capabilities_uri = serializers.CharField()
    service_metadata_uri = serializers.CharField()
    fees = serializers.CharField()
    access_constraints = serializers.CharField()
    terms_of_use = serializers.PrimaryKeyRelatedField(read_only=True)
    service = ServiceSerializer(read_only=True)
    organization = OrganizationSerializer(read_only=True, source="contact")
    related_metadata = MetadataRelationSerializer(many=True)
    keywords = KeywordSerializer(read_only=True, many=True)
    categories = serializers.PrimaryKeyRelatedField(read_only=True, many=True)


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
