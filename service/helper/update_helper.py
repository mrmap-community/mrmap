"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.06.19

"""
from copy import copy

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from service.models import Service, Layer, FeatureType, Metadata


def transform_lists_to_m2m_collections(element):
    """ Iterates over all non-persisting attributes (take a look in the service models) and stores the items in the M2M relations.

    Since we have to deal with the database objects without having them persisted (e.g. for comparison), we need to
    workaround the fact that a not persisted object can not have a M2M collection with other objects (e.g. metadata-keywords).
    These items are stored temporarily in simple lists and have to be moved into their M2M containers during persisting.
    This function simplifies the work by iterating over everything and putting it at the right place.

    NOTE:
        element MUST be persisted before (element.save()) use

    Args:
        element: An element of the type Metadata, Service or FeatureType
    Returns:
         element: The element
    """
    if isinstance(element, FeatureType):
        # featuretype transforming of lists
        # additional srs
        for srs in element.additional_srs_list:
            element.additional_srs.add(srs)

        # keywords
        for kw in element.keywords_list:
            element.keywords.add(kw)

        # formats
        for _format in element.formats_list:
            element.formats.add(_format)

        # elements
        for e in element.elements_list:
            element.elements.add(e)

        # namespaces
        for ns in element.namespaces_list:
            element.namespaces.add(ns)

    elif isinstance(element, Metadata):
        # metadata transforming of lists
        # keywords
        for kw in element.keywords_list:
            element.keywords.add(kw)
        # reference systems
        for srs in element.reference_system_list:
            element.reference_system.add(srs)

    elif isinstance(element, Service):
        # service transforming of lists
        # formats
        for _format in element.formats_list:
            element.formats.add(_format)

        # categories
        for category in element.categories_list:
            element.categories.add(category)

    else:
        raise Exception("UNKNOWN INSTANCE!")
    return element

@transaction.atomic
def update_metadata(old: Metadata, new: Metadata):
    """ Overwrites existing metadata (old) with newer content (new).

    Database related information like id, created_by, and so on is saved before and written back after overwriting.

    Args:
        old (Metadata): The existing metadata, that shall be overwritten
        new (Metadata): The new metadata that is used for overwriting
    Returns:
         old (Metadata): The overwritten metadata
    """
    # save important persistance information
    uuid = old.uuid
    _id = old.id
    created_by = old.created_by
    created_on = old.created

    # overwrite old information with new one
    old = copy(new)
    old.id = _id
    old.uuid = uuid
    old.created = created_on
    old.created_by = created_by

    # keywords
    old.keywords.clear()
    for kw in new.keywords_list:
        old.keywords.add(kw)
    # reference systems
    old.reference_system.clear()
    for srs in new.reference_system_list:
        old.reference_system.add(srs)

    return old

@transaction.atomic
def update_service(old: Service, new: Service):
    """ Overwrites existing service (old) with newer content (new).

    Database related information like id, created_by, and so on is saved before and written back after overwriting.

    Args:
        old (Service): The existing metadata, that shall be overwritten
        new (Service): The new metadata that is used for overwriting
    Returns:
         old (Service): The overwritten metadata
    """
    # save important persistance information
    uuid = old.uuid
    _id = old.id
    created_by = old.created_by
    created_on = old.created
    published_for = old.published_for

    # overwrite old information with new one
    old = copy(new)
    old.id = _id
    old.uuid = uuid
    old.created = created_on
    old.created_by = created_by
    old.published_for = published_for

    # formats
    old.formats.clear()
    for _format in new.formats_list:
        old.formats.add(_format)

    # categories
    old.categories.clear()
    for category in new.categories_list:
        old.categories.add(category)

    return old

@transaction.atomic
def update_feature_type(old: FeatureType, new: FeatureType):
    """ Overwrites existing feature type (old) with newer (new).

    Database related information like id, created_by, and so on is saved before and written back after overwriting.

    Args:
        old (FeatureType): The existing metadata, that shall be overwritten
        new (FeatureType): The new metadata that is used for overwriting
    Returns:
         old (FeatureType): The overwritten metadata
    """
    # save important persistance information
    uuid = old.uuid
    _id = old.id
    created_by = old.created_by
    created_on = old.created
    service = old.service

    # overwrite old information with new one
    old = copy(new)
    old.id = _id
    old.uuid = uuid
    old.created = created_on
    old.created_by = created_by
    old.service = service


    # additional srs
    old.additional_srs.clear()
    for srs in new.additional_srs_list:
        old.additional_srs.add(srs)

    # keywords
    old.keywords.clear()
    for kw in new.keywords_list:
        old.keywords.add(kw)

    # formats
    old.formats.clear()
    for _format in new.formats_list:
        old.formats.add(_format)

    # elements
    old.elements.clear()
    for element in new.elements_list:
        old.elements.add(element)

    # namespaces
    old.namespaces.clear()
    for ns in new.namespaces_list:
        old.namespaces.add(ns)

    return old

@transaction.atomic
def update_single_layer(old: Layer, new: Layer):
    """ Overwrites existing layer (old) with newer (new).

    Database related information like id, created_by, and so on is saved before and written back after overwriting.

    Args:
        old (Layer): The existing metadata, that shall be overwritten
        new (Layer): The new metadata that is used for overwriting
    Returns:
         old (Layer): The overwritten metadata
    """
    # save important persistance information
    uuid = old.uuid
    _id = old.id
    identifier = old.identifier
    created_by = old.created_by
    created_on = old.created
    parent_service = old.parent_service
    parent_layer = old.parent_layer

    # overwrite old information with new one
    old = copy(new)
    old.id = _id
    old.identifier = identifier
    old.uuid = uuid
    old.created = created_on
    old.created_by = created_by
    old.parent_service = parent_service
    old.parent_layer = parent_layer

    # save metadata
    md = old.metadata
    md.save()
    md = transform_lists_to_m2m_collections(md)
    old.metadata = md
    old.save()
    old = transform_lists_to_m2m_collections(old)

    return old

@transaction.atomic
def update_wfs(old: Service, new: Service, diff: dict, links: dict):
    """ Updates the whole wfs service

    Goes through all data, starting at metadata, down to feature types and it's elements to update the current status.
    Adds new elements, updates existing ones and removes (also from DB) deprecated ones.

    Args:
        old (Service): The already existing service
        new (Service): The temporary loaded new version of the old service
        diff (dict): The differences that have been found during comparison before
        links (dict): Contains key/value pairs of old_identifier->new_identifier (needed for renamed layers or feature types)
    Returns:
         old (Service): The updated service
    """
    # update, add and remove feature types
    # feature types
    old_service_feature_types = FeatureType.objects.filter(service=old)
    for feature_type in new.feature_type_list:
        name = feature_type.name
        rename = False

        if feature_type.name in links.keys():
            # aha! This layer is just a renamed one, that already exists. It must be updated and renamed!
            name = links[feature_type.name]
            rename = True

        existing_f_t = old_service_feature_types.filter(name=name)
        if existing_f_t.count() == 0:
            # does not exist -> must be new
            # add the new feature type
            feature_type.service = old
            feature_type.save()
            transform_lists_to_m2m_collections(feature_type)
            old.featuretypes.add(feature_type)
        elif existing_f_t.count() == 1:
            # exists already and needs to be overwritten
            existing_f_t = existing_f_t[0]
            if rename:
                existing_f_t.name = feature_type.name
            existing_f_t.save()
            #transform_lists_to_m2m_collections(existing_f_t)
            existing_f_t = update_feature_type(existing_f_t, feature_type)
            existing_f_t.save()
    # remove old featuretypes
    for removable in diff["feature_types"]["removed"]:
        #old.featuretypes.remove(removable)
        try:
            pers_feature_type = FeatureType.objects.get(service=old, name=removable.name)
            pers_feature_type.delete()
        except ObjectDoesNotExist:
            pass

    return old


@transaction.atomic
def _update_wms_layers_recursive(old: Service, new: Service, layers: list, links: dict, parent: Layer = None):
    """ Updates wms layers recursively.

    Iterates over all children on level 1, adds new layers, updates existing ones, removes old ones, then proceeds
    on the children of each layer on the next level and so on.

    Args:
        old (Service): The existing service that nees to be updated
        new (Service): The newer version from where the new data is taken
        layers (list): The current list of children
    Returns:
         old (Service): The updated existing service
    """
    for layer in layers:
        identifier = layer.identifier
        rename = False

        if layer.identifier in links.keys():
            # aha! This layer is just a renamed one, that already exists. It must be updated and renamed!
            identifier = links[layer.identifier]
            rename = True
        # check if layer already exists
        existing_layer = Layer.objects.filter(parent_service=old, identifier=identifier)
        if existing_layer.count() == 0:
            # not existing yet -> add it!
            layer.parent_service = old
            layer.parent_layer = parent
            md = layer.metadata
            md.save()
            transform_lists_to_m2m_collections(md)
            layer.metadata = md
            layer.save()
            layer = transform_lists_to_m2m_collections(layer)
        elif existing_layer.count() == 1:
            # existing -> update it!
            existing_layer = existing_layer[0]
            if rename:
                existing_layer.identifier = layer.identifier
            existing_layer.save()
            existing_layer = update_single_layer(existing_layer, layer)
            # for parent-child connection we need to put the existing layer into the running variable layer
            layer = existing_layer

        children = layer.children_list
        if len(children) > 0:
            _update_wms_layers_recursive(old, new, children, links, layer)

@transaction.atomic
def update_wms(old: Service, new: Service, diff: dict, links: dict):
    """ Updates a whole wms service

    Handles all metadata and layers.

    Args:
        old (Service): The existing service that nees to be updated
        new (Service): The newer version from where the new data is taken
        diff (dict): The differences that have been found before between the old and new service
        links (dict): Contains key/value pairs of old_identifier->new_identifier (needed for renamed layers or feature types)
    Returns:
         old (Service): The updated existing service
    """
    _update_wms_layers_recursive(old, new, [new.root_layer], links=links)
    # remove unused layers
    for layer in diff["layers"]["removed"]:
        # find persisted layer at first
        try:
            pers_layer = Layer.objects.get(parent_service=old, identifier=layer.identifier)
            pers_layer.delete()
        except ObjectDoesNotExist:
            # This will happen if a layer is deleted which has child layers. The parent will kill it's children instantly.
            # Therefore the children won't be found when the ORM tries to fetch them from the database...
            pass
    return old
