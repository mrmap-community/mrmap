"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 21.01.20

"""

from django.http import HttpRequest
from django_tables2 import RequestConfig

from MrMap.consts import DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE
from service.helper.enums import MetadataEnum
from service.models import Metadata, Organization, Layer, FeatureType, MetadataRelation, Service
from structure.models import MrMapUser
from service.filters import ChildLayerFilter, FeatureTypeFilter
from service.tables import ChildLayerTable, FeatureTypeTable, CoupledMetadataTable

per_page = 5
default_page = 1


def collect_contact_data(organization: Organization):
    contact = {'organization_name': organization.organization_name, 'email': organization.email,
               'address_country': organization.country, 'street_address': organization.address,
               'address_region': organization.state_or_province, 'postal_code': organization.postal_code,
               'address_locality': organization.city, 'person_name': organization.person_name,
               'telephone': organization.phone}

    # prevents None values
    for key in contact:
        if contact[key] is None:
            contact[key] = ''

    return contact


def collect_featuretype_data(md: Metadata):
    params = {}

    if md.featuretype.parent_service.published_for is not None:
        params['contact'] = collect_contact_data(md.featuretype.parent_service.published_for)

    if md.featuretype.parent_service:
        params['parent_service'] = md.featuretype.parent_service
        params['fees'] = md.featuretype.parent_service.metadata.fees

    params['bounding_box'] = md.bounding_geometry
    params['name_of_the_resource'] = md.identifier
    params['featuretype'] = md.featuretype
    params['abstract'] = md.featuretype.parent_service.metadata.abstract
    params['access_constraints'] = md.featuretype.parent_service.metadata.access_constraints

    # TODO: build schema link:
    # schema: describe_layer_uri_GET
    # SERVICE=WFS&VERSION=1.0.0&REQUEST=DescribeFeatureType&typeName=verwaltungsgrenzen_rp.fcgi_landkreise_rlp_Polygon

    return params


def collect_layer_data(md: Metadata, request: HttpRequest):
    params = {}

    # if there is a published_for organization it will be presented
    if md.service.published_for is not None:
        params['contact'] = collect_contact_data(md.service.published_for)

    params['layer'] = md.service.layer
    params['name_of_the_resource'] = md.service.layer.identifier
    params['is_queryable'] = md.service.layer.is_queryable
    params['bounding_box'] = md.bounding_geometry

    if md.service.parent_service:
        params['parent_service'] = md.service.parent_service
        params['fees'] = md.service.parent_service.metadata.fees

    try:
        # is it a root layer?
        params['parent_layer'] = Layer.objects.get(
            child_layers=md.service.layer
        )
    except Layer.DoesNotExist:
        # yes, it's a root layer, no parent available; skip
        None

    # get sublayers
    child_layers = Layer.objects.filter(
        parent_layer=md.service
    )

    # if child_layers > 0 collect more data about the child layers
    if child_layers.count() > 0:
        # filter queryset
        child_layers_filtered = ChildLayerFilter(request.GET, queryset=child_layers)
        params['layer_filter'] = child_layers_filtered

        children = []
        for child in child_layers_filtered.qs:
            # search for sub children
            child_child_layers = Layer.objects.filter(
                parent_layer=child
            )

            children.append({'id': child.metadata.id,
                             'title': child.metadata.title,
                             'sublayers_count': child_child_layers.count()}, )

        child_layer_table = ChildLayerTable(data=children,
                                            order_by='title',
                                            request=None,)

        child_layer_table.configure_pagination(request, 'cl-t')

        params['children'] = child_layer_table

    return params


def collect_wms_root_data(md: Metadata):
    params = {}

    # if there is a published_for organization it will be presented
    if md.service.published_for is not None:
        params['contact'] = collect_contact_data(md.service.published_for)

    # first layer item
    layer = Layer.objects.get(
        parent_service=md.service,
        parent_layer=None,
    )

    params['bounding_box'] = md.bounding_geometry
    params['layer'] = layer
    params['name_of_the_resource'] = layer.identifier
    params['is_queryable'] = layer.is_queryable

    # search for sub children
    child_child_layers = Layer.objects.filter(
        parent_layer=layer
    )
    sub_layer = [{'id': layer.metadata.id,
                  'title': layer.metadata.title,
                  'sublayers_count': child_child_layers.count()}]

    sub_layer_table = ChildLayerTable(data=sub_layer,
                                      orderable=False,
                                      show_header=False,
                                      request=None,)

    params['children'] = sub_layer_table
    params['fees'] = md.fees

    return params


def collect_wfs_root_data(md: Metadata, request: HttpRequest):
    params = {}

    # if there is a published_for organization it will be presented
    if md.service.published_for is not None:
        params['contact'] = collect_contact_data(md.service.published_for)

    params['fees'] = md.service.metadata.fees

    featuretypes = FeatureType.objects.filter(
        parent_service=md.service
    )

    featuretypes_filtered = FeatureTypeFilter(request.GET, queryset=featuretypes)
    params['featuretypes_filter'] = featuretypes_filtered

    # if child_layers > 0 collect more data about the child layers

    featuretypes = []
    for child in featuretypes_filtered.qs:
        # search for sub children

        featuretypes.append({'id': child.metadata.id,
                             'title': child.metadata.title,
                             })

    featuretype_table = FeatureTypeTable(data=featuretypes,
                                         order_by='title',
                                         request=None,)
    featuretype_table.configure_pagination(request, 'ft-t')
    featuretype_table.filter = featuretypes_filtered

    params['featuretypes'] = featuretype_table
    params['bounding_box'] = md.bounding_geometry

    return params


def collect_metadata_related_objects(md: Metadata, request: HttpRequest,):
    params = {}

    # get all related Metadata objects
    metadata_relations = MetadataRelation.objects.filter(
        metadata_from=md,
        metadata_to__metadata_type__type=MetadataEnum.DATASET.value
    )

    # if no related metadata found, skip
    if metadata_relations.count() > 0:
        # convert MetadataRelation Objects to Metadata object
        metadatas_object_array = [metadata_relation.metadata_to for metadata_relation in metadata_relations]

        metadatas_dict_array = []
        for metadata in metadatas_object_array:
            metadatas_dict_array.append({'id': metadata.id, 'title': metadata.title})

        show_header = False
        if metadata_relations.count() > 1:
            show_header = True

        # build django tables2 table
        related_metadata_table = CoupledMetadataTable(
            data=metadatas_dict_array,
            order_by='title',
            show_header=show_header,
            request=None,)

        related_metadata_table.configure_pagination(request, 'rm-t')

        params['related_metadata'] = related_metadata_table

    return params
