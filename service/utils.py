"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 21.01.20

"""

from django.http import HttpRequest
from service.models import Metadata, Organization, Layer, FeatureType
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
        params['licence'] = md.featuretype.parent_service.metadata.licence

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
        params['licence'] = md.service.parent_service.metadata.licence

    if md.service.layer.is_root_node():
        params['parent'] = md.service.layer

    # get sublayers
    child_layers = md.service.get_descendants()

    # if child_layers > 0 collect more data about the child layers
    if child_layers.count() > 0:
        # filter queryset
        child_layers_filtered = ChildLayerFilter(request.GET, queryset=child_layers)
        params['layer_filter'] = child_layers_filtered

        children = []
        for child in child_layers_filtered.qs:
            # search for sub children
            child_child_layers = child.get_children()
            children.append({'id': child.metadata.id,
                             'title': child.metadata.title,
                             'sublayers_count': child_child_layers.count()}, )

        child_layer_table = ChildLayerTable(queryset=children,
                                            order_by='title',
                                            request=request,)

        params['children'] = child_layer_table

    return params


def collect_wms_root_data(md: Metadata, request: HttpRequest):
    params = {}

    # if there is a published_for organization it will be presented
    if md.service.published_for is not None:
        params['contact'] = collect_contact_data(md.service.published_for)

    # first layer item
    layer = Layer.objects.get(
        parent_service=md.service,
        parent=None,
    )

    params['bounding_box'] = md.bounding_geometry
    params['layer'] = layer
    params['name_of_the_resource'] = layer.identifier
    params['is_queryable'] = layer.is_queryable

    # search for sub children
    child_child_layers = Layer.objects.filter(
        parent=layer
    )
    sub_layer = [{'id': layer.metadata.id,
                  'title': layer.metadata.title,
                  'sublayers_count': child_child_layers.count()}]

    sub_layer_table = ChildLayerTable(queryset=sub_layer,
                                      orderable=False,
                                      show_header=False,
                                      request=request,)

    params['children'] = sub_layer_table
    params['fees'] = md.fees
    params['licence'] = md.licence

    return params


def collect_wfs_root_data(md: Metadata, request: HttpRequest):
    params = {}

    # if there is a published_for organization it will be presented
    if md.service.published_for is not None:
        params['contact'] = collect_contact_data(md.service.published_for)

    params['fees'] = md.service.metadata.fees
    params['licence'] = md.service.metadata.licence

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

    featuretype_table = FeatureTypeTable(queryset=featuretypes,
                                         order_by='title',
                                         request=request,)

    params['featuretypes'] = featuretype_table
    params['bounding_box'] = md.bounding_geometry

    return params


def collect_metadata_related_objects(md: Metadata, request: HttpRequest,):
    params = {}

    # get all related Metadata objects from type dataset
    related_metadatas = md.get_related_dataset_metadatas()
    if related_metadatas:
        # build django tables2 table
        related_metadatas_table = CoupledMetadataTable(
            queryset=related_metadatas,
            order_by='title',
            show_header=True,
            request=request,
            param_lead='rm-t')

        params['related_metadatas'] = related_metadatas

    return params
