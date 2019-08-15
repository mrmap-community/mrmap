"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.08.19

"""
from rest_framework import serializers

from service.models import Service, Layer, Metadata, ServiceType


class ServiceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceType
        fields = [
            "name",
            "version"
        ]

class MetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = Metadata
        fields = [
            "id",
            "identifier",
            "title",
            "abstract",
            "online_resource",
            "original_uri",
        ]

class ServiceSerializer(serializers.ModelSerializer):
    metadata = MetadataSerializer()
    class Meta:
        model = Service
        fields = [
            "id",
            "uuid",
            "metadata",
            "is_available",
            "is_active",
            "servicetype"
        ]


class LayerSerializer(serializers.ModelSerializer):
    metadata = MetadataSerializer()
    parent_service = ServiceSerializer()
    servicetype = ServiceTypeSerializer()
    class Meta:
        model = Layer
        fields = [
            "id",
            "uuid",
            "identifier",
            "metadata",
            "is_available",
            "is_active",
            "parent_service",
            "servicetype"
        ]
