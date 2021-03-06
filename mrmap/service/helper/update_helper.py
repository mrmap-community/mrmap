"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.06.19

"""
from copy import deepcopy

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from editor.forms import MetadataEditorForm
from service.helper.enums import DocumentEnum
from service.models import Service, Layer, FeatureType, Metadata, ReferenceSystem, MimeType, Document


@transaction.atomic
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
        # elements
        element.elements.add(*element.elements_list)

        # namespaces
        element.namespaces.add(*element.namespaces_list)

        # additional srs
        element.metadata.reference_system.add(*element.additional_srs_list)

    elif isinstance(element, Metadata):
        # metadata transforming of lists
        # keywords
        element.keywords.add(*element.keywords_list)

        # Reference systems
        for srs in element.reference_system_list:
            srs = ReferenceSystem.objects.get_or_create(code=srs.code, prefix=srs.prefix)[0]
            element.reference_system.add(srs)

        # formats
        for _format in element.formats_list:
            _format = MimeType.objects.get_or_create(
                operation=_format.operation,
                mime_type=_format.mime_type,
            )[0]
            element.formats.add(_format)

        # categories
        element.categories.add(*element.categories_list)

    elif isinstance(element, Service):
        # service transforming of lists
        pass

    else:
        raise Exception("UNKNOWN INSTANCE!")
    return element


def update_capability_document(current_service: Service, new_service: Service):
    """ Updates the Document object, related to the resource/metadata

    Args:
        current_service (Service):
        new_service (Service):
    Returns:
         nothing
    """
    cap_document = current_service.metadata.documents.get(is_original=True, document_type=DocumentEnum.CAPABILITY.value)
    cap_document.content = new_service.metadata.documents.get(is_original=True, document_type=DocumentEnum.CAPABILITY.value).content
    cap_document.save()

    # Remove cached document
    current_service.metadata.clear_cached_documents()

    # By deleting the current capability document, the system is forced to create a current capability document from the
    # state at this time
    current_cap_doc = Document.objects.filter(
        metadata=current_service.metadata,
        is_original=False,
        document_type=DocumentEnum.CAPABILITY.value
    )
    current_cap_doc.delete()


@transaction.atomic
def update_metadata(old: Metadata, new: Metadata, keep_custom_md: bool):
    """ Overwrites existing metadata (old) with newer content (new).

    Database related information like id, created_by, and so on is saved before and written back after overwriting.

    Args:
        old (Metadata): The existing metadata, that shall be overwritten
        new (Metadata): The new metadata that is used for overwriting
    Returns:
         old (Metadata): The overwritten metadata
    """
    # reset update candidate
    new.is_update_candidate_for = None

    # Save important persistance information
    _id = old.id
    created_by = old.created_by
    created_on = old.created
    activated = old.is_active
    metadata_type = old.metadata_type
    metadata_is_custom = old.is_custom

    # If needed, cache custom metadata
    custom_md = {}
    if keep_custom_md:
        custom_md_fields = MetadataEditorForm._meta.fields
        for field in custom_md_fields:
            custom_md[field] = old.__getattribute__(field)
        del custom_md_fields

    # Overwrite old information with new one
    old = deepcopy(new)
    old.id = _id
    old.created = created_on
    old.created_by = created_by
    old.is_active = activated
    old.metadata_type = metadata_type

    # reference systems
    old.reference_system.clear()
    old.reference_system.add(*new.reference_system.all())

    # Dimensions
    old.dimensions.clear()
    old.dimensions.add(*new.dimensions.all())

    # formats
    old.formats.clear()
    old.formats.add(*new.formats_list)

    # Restore custom metadata if needed
    if keep_custom_md:
        old.is_custom = metadata_is_custom
        for key, val in custom_md.items():
            # ManyRelatedManagers have to be handled differently
            try:
                old.__setattr__(key, val)
            except TypeError:
                # If the above simple attribute setter fails, we are dealing with a ManyRelatedManager, that has to be
                # handled differently
                field = val.prefetch_cache_name
                old_manager = old.__getattribute__(field)
                old_manager_elems = old_manager.all()
                custom_m2m_elements = val.all()
                for elem in custom_m2m_elements:
                    if elem not in old_manager_elems:
                        old_manager.add(elem)
    else:
        # Keywords updating without keeping custom md
        old.keywords.clear()
        old.keywords.add(*new.keywords.all())

    old.last_modified = timezone.now()
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
    # reset update candidate
    new.is_update_candidate_for = None

    # save important persistance information
    _id = old.id
    created_by = old.created_by
    created_on = old.created
    published_for = old.published_for
    md = old.metadata  # metadata is expected to be updated already at this point. Therefore we need to keep it!
    activated = old.is_active

    # overwrite old information with new one
    old = deepcopy(new)
    old.id = _id
    old.created = created_on
    old.created_by = created_by
    old.published_for = published_for
    old.metadata = md
    old.is_active = activated

    old.last_modified = timezone.now()
    return old


@transaction.atomic
def update_feature_type(old: FeatureType, new: FeatureType, keep_custom_metadata: bool = False):
    """ Overwrites existing feature type (old) with newer (new).

    Database related information like id, created_by, and so on is saved before and written back after overwriting.

    Args:
        old (FeatureType): The existing metadata, that shall be overwritten
        new (FeatureType): The new metadata that is used for overwriting
        keep_custom_metadata (bool): Whether the metadata shall be overwritten or not
    Returns:
         old (FeatureType): The overwritten metadata
    """
    # save important persistance information
    _id = old.id
    created_by = old.created_by
    created_on = old.created
    service = old.parent_service
    metadata = old.metadata

    # overwrite old information with new one
    old = deepcopy(new)
    old.id = _id
    old.created = created_on
    old.created_by = created_by
    old.parent_service = service

    old.metadata = update_metadata(metadata, new.metadata, keep_custom_metadata)

    return old


@transaction.atomic
def update_single_layer(old: Layer, new: Layer, keep_custom_metadata: bool = False):
    """ Overwrites existing layer (old) with newer (new).

    Database related information like id, created_by, and so on is saved before and written back after overwriting.

    Args:
        old (Layer): The existing metadata, that shall be overwritten
        new (Layer): The new metadata that is used for overwriting
        keep_custom_metadata (bool): Whether the metadata should be kept or overwritten
    Returns:
         old (Layer): The overwritten metadata
    """
    # save important persistance information
    _id = old.id
    created_by = old.created_by
    created_on = old.created
    parent_service = old.parent_service
    parent = old.parent
    metadata = old.metadata
    active = old.is_active

    # Overwrite old information with new one
    old = deepcopy(new)

    # Restore important information
    old.id = _id
    old.created = created_on
    old.created_by = created_by
    old.parent_service = parent_service
    old.parent = parent
    old.metadata = metadata
    old.is_active = active

    old.metadata = update_metadata(metadata, new.metadata, keep_custom_metadata)

    old.metadata.save()
    old.save()
    return old


@transaction.atomic
def update_wfs_elements(old: Service, new: Service, diff: dict, links: dict, keep_custom_metadata: bool = False):
    """ Updates the whole wfs service

    Goes through all data, starting at metadata, down to feature types and it's elements to update the current status.
    Adds new elements, updates existing ones and removes (also from DB) deprecated ones.

    Args:
        old (Service): The already existing service
        new (Service): The temporary loaded new version of the old service
        diff (dict): The differences that have been found during comparison before
        links (dict): Contains key/value pairs of old_identifier->new_identifier (needed for renamed layers or feature types)
        keep_custom_metadata (bool): Whether the feature types should be overwritten or simply added/removed
    Returns:
         old (Service): The updated service
    """
    # update, add and remove feature types
    # feature types
    old_service_feature_types = FeatureType.objects.filter(parent_service=old)
    new_service_feature_types = FeatureType.objects.filter(parent_service=new)
    for feature_type in new_service_feature_types:
        id = None
        existing_f_t = None

        try:
            if feature_type.metadata.identifier in links.keys():
                # This FeatureType is just a renamed one, that already exists. It must be updated and renamed!
                # Get the id, from the FeatureType that already exist
                id = links[feature_type.metadata.identifier]
            else:
                existing_f_t = FeatureType.objects.get(
                    parent_service=old,
                    metadata__identifier=feature_type.metadata.identifier,
                )
            if existing_f_t is None:
                # Try to get this FeatureType (will fail for id=-1 -> indicates new FeatureType
                # but no linking to old FeatureType)
                existing_f_t = old_service_feature_types.get(metadata__id=id)

            existing_f_t = update_feature_type(existing_f_t, feature_type, keep_custom_metadata)
            existing_f_t.save()

        except ObjectDoesNotExist:
            # FeatureType could not be found with the given information.
            # FeatureType must be new  -> add it!
            feature_type.parent_service = old
            feature_type.is_active = old.is_active
            md = feature_type.metadata
            md.is_active = old.is_active
            md.metadata_type = md.metadata_type
            md.save()

            transform_lists_to_m2m_collections(md)
            feature_type.metadata = md
            feature_type.save()
            feature_type = transform_lists_to_m2m_collections(feature_type)
            feature_type.save()

    # remove old featuretypes
    for removable in diff["feature_types"]["removed"]:
        try:
            pers_feature_type = FeatureType.objects.get(parent_service=old, metadata__identifier=removable.metadata.identifier)
            pers_feature_type.delete()
        except ObjectDoesNotExist:
            pass
    return old


@transaction.atomic
def _update_wms_layers(old: Service, root_layer: Layer, links: dict,
                       keep_custom_metadata: bool = False):
    """ Updates wms layers

    Iterates over all children on level 1, adds new layers, updates existing ones, removes old ones, then proceeds
    on the children of each layer on the next level and so on.

    Args:
        old (Service): The existing service that needs to be updated
        root_layer (Layer): The root layer where we start searching for descendants
        keep_custom_metadata (bool): Whether the metadata should be overwritten or not
    Returns:
         old (Service): The updated existing service
    """
    descendants = root_layer.get_descendants(include_self=True)
    parent = None
    for new_layer in descendants:
        keys = links.keys()
        existing_layer = None
        id = None

        # Update layer
        try:
            if new_layer.identifier in keys:
                # Get the id, from the layer that already exist
                id = links[new_layer.identifier]
            else:
                # if the layer is not new, we just want to update it
                existing_layer = Layer.objects.get(
                    parent_service=old,
                    identifier=new_layer.identifier
                )
            # If no existing_layer could be found until now, we assume the id variable to be set. This means, that
            # the user knows, that an existing layer has been renamed to the new one. We fetch the "old" layer now...
            if existing_layer is None:
                existing_layer = Layer.objects.get(metadata__id=id)

            # ... and perform the update on it.
            update_single_layer(existing_layer, new_layer, keep_custom_metadata)

        except ObjectDoesNotExist:
            # Layer could not be found with the given information.
            # Layer must be new  -> add it!
            new_layer.parent_service = old
            new_layer.parent = parent
            new_layer.is_active = old.is_active
            md = new_layer.metadata
            md.is_active = old.is_active
            md.save()

            transform_lists_to_m2m_collections(md)
            new_layer.metadata = md
            new_layer.save()
            new_layer = transform_lists_to_m2m_collections(new_layer)

        finally:
            parent = new_layer


@transaction.atomic
def _update_wms_layers_recursive(old: Service, new: Service, new_layers: list, links: dict, parent: Layer = None, keep_custom_metadata: bool = False):
    """ Updates wms layers recursively.

    Iterates over all children on level 1, adds new layers, updates existing ones, removes old ones, then proceeds
    on the children of each layer on the next level and so on.

    Args:
        old (Service): The existing service that needs to be updated
        new (Service): The newer version from where the new data is taken
        new_layers (list): The list of children from last recursion call to iterae
        keep_custom_metadata (bool): Whether the metadata should be overwritten or not
    Returns:
         old (Service): The updated existing service
    """
    for new_layer in new_layers:
        keys = links.keys()
        existing_layer = None
        id = None

        # Update layer
        try:
            if new_layer.identifier in keys:
                # Get the id, from the layer that already exist
                id = links[new_layer.identifier]
            else:
                # if the layer is not new, we just want to update it
                existing_layer = Layer.objects.get(
                    parent_service=old,
                    identifier=new_layer.identifier
                )
            # If no existing_layer could be found until now, we assume the id variable to be set. This means, that
            # the user knows, that an existing layer has been renamed to the new one. We fetch the "old" layer now...
            if existing_layer is None:
                existing_layer = Layer.objects.get(metadata__id=id)

            # ... and perform the update on it.
            update_single_layer(existing_layer, new_layer, keep_custom_metadata)

        except ObjectDoesNotExist:
            # Layer could not be found with the given information.
            # Layer must be new  -> add it!
            new_layer.parent_service = old
            new_layer.parent = parent
            new_layer.is_active = old.is_active
            md = new_layer.metadata
            md.is_active = old.is_active
            md.metadata_type = md.metadata_type
            md.save()

            transform_lists_to_m2m_collections(md)
            new_layer.metadata = md
            new_layer.save()
            new_layer = transform_lists_to_m2m_collections(new_layer)
            new_layer.save()

        children_of_new = new_layer.child_layers.all()
        _update_wms_layers_recursive(old, new, children_of_new, links, new_layer, keep_custom_metadata)


@transaction.atomic
def update_wms_elements(old: Service, new: Service, diff: dict, links: dict, keep_custom_metadata: bool = False):
    """ Updates a whole wms service

    Handles all metadata and layers.

    Args:
        old (Service): The existing service that needs to be updated
        new (Service): The newer version from where the new data is taken
        diff (dict): The differences that have been found before between the old and new service
        links (dict): Contains key/value pairs of old_identifier->new_identifier (needed for renamed layers or feature types)
        keep_custom_metadata (bool): Whether the metadata should be overwritten or simply new elements be added/old removed
    Returns:
         old (Service): The updated existing service
    """
    # _update_wms_layers_recursive(old, new, [new.root_layer], links=links, keep_custom_metadata=keep_custom_metadata)
    _update_wms_layers(old, new.root_layer, links=links, keep_custom_metadata=keep_custom_metadata)

    # remove unused layers
    identifieres = [layer.identifier for layer in diff["layers"]["removed"]]
    Layer.objects.filter(parent_service=old, identifier__in=identifieres).delete()
    return old
