"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 01.08.19

"""
import json
import urllib

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest

from lxml.etree import _Element
from requests.exceptions import MissingSchema

from MapSkinner.cacher import DocumentCacher
from MapSkinner.messages import EDITOR_INVALID_ISO_LINK, SECURITY_PROXY_MUST_BE_ENABLED_FOR_SECURED_ACCESS, \
    SECURITY_PROXY_MUST_BE_ENABLED_FOR_LOGGING, SECURITY_PROXY_DEACTIVATING_NOT_ALLOWED
from MapSkinner.settings import XML_NAMESPACES, HOST_NAME, HTTP_OR_SSL, GENERIC_NAMESPACE_TEMPLATE
from MapSkinner import utils

from service.helper.enums import OGCServiceVersionEnum, OGCServiceEnum, OGCOperationEnum, MetadataEnum
from service.helper.iso.iso_metadata import ISOMetadata
from service.models import Metadata, Keyword, Category, FeatureType, Document, MetadataRelation, \
    MetadataOrigin, SecuredOperation, RequestOperation, Layer, Style
from service.helper import xml_helper
from service.settings import MD_RELATION_TYPE_DESCRIBED_BY
from service.tasks import async_secure_service_task


def _overwrite_capabilities_keywords(xml_obj: _Element, metadata: Metadata, _type: str):
    """ Overwrites existing capabilities keywords with metadata editor input

    Args:
        xml_obj (_Element): The parent xml object which holds the KeywordList element
        metadata (Metadata): The metadata object which holds the edited keyword data
        _type (str): Defines if this is a wms or wfs
    Returns:
         nothing
    """
    ns_prefix = ""
    keyword_container_tag = "KeywordList"
    keyword_prefix = ""
    keyword_ns_map = {}

    if _type == 'wfs':
        ns_keyword_prefix_s = "ows"
        ns_prefix = "wfs:"
        if metadata.is_root():
            # for the <ows:ServiceIdentification> element we need the prefix "ows:"
            ns_prefix = "ows:"
        keyword_container_tag = "Keywords"
        keyword_prefix = "{" + XML_NAMESPACES[ns_keyword_prefix_s] + "}"
        keyword_ns_map[ns_keyword_prefix_s] = XML_NAMESPACES[ns_keyword_prefix_s]

    xml_keywords_list_obj = xml_helper.try_get_single_element_from_xml("./" + GENERIC_NAMESPACE_TEMPLATE.format(keyword_container_tag), xml_obj)

    if xml_keywords_list_obj is None:
        # there are no keywords in this capabilities for this element yet
        # we need to add an element first!
        try:
            xml_keywords_list_obj = xml_helper.create_subelement(xml_obj, "{}{}".format(keyword_prefix, keyword_container_tag), after="{}Abstract".format(ns_prefix), nsmap=keyword_ns_map)
        except (TypeError, ValueError) as e:
            # there seems to be no <Abstract> element. We add simply after <Title> and also create a new Abstract element
            xml_keywords_list_obj = xml_helper.create_subelement(xml_obj, "{}{}".format(keyword_prefix, keyword_container_tag), after="{}Title".format(ns_prefix))
            xml_helper.create_subelement(
                xml_obj,
                "{}".format("Abstract"),
                after="{}Title".format(ns_prefix)
            )

    xml_keywords_objs = xml_helper.try_get_element_from_xml(
        "./" + GENERIC_NAMESPACE_TEMPLATE.format("Keyword"),
        xml_keywords_list_obj
    ) or []

    # first remove all persisted keywords
    for kw in xml_keywords_objs:
        xml_keywords_list_obj.remove(kw)

    # then add all edited
    for kw in metadata.keywords.all():
        xml_keyword = xml_helper.create_subelement(xml_keywords_list_obj, "{}Keyword".format(keyword_prefix), nsmap=keyword_ns_map)
        xml_helper.write_text_to_element(xml_keyword, txt=kw.keyword)


def _overwrite_capabilities_iso_metadata_links(xml_obj: _Element, metadata: Metadata):
    """ Overwrites links in capabilities document

    Args:
        xml_obj (_Element): The xml_object of the document
        metadata (Metadata): The metadata object, holding the data
    Returns:

    """
    # get list of all iso md links that really exist (from the metadata object)
    iso_md_links = metadata.get_related_metadata_uris()

    # get list of all MetadataURL elements from the capabilities element
    xml_links = xml_helper.try_get_element_from_xml("./MetadataURL", xml_obj)
    for xml_link in xml_links:
        xml_online_resource_elem = xml_helper.try_get_element_from_xml("./OnlineResource", xml_link)
        xml_link_attr = xml_helper.try_get_attribute_from_xml_element(xml_online_resource_elem, "xlink:href")
        if xml_link_attr in iso_md_links:
            # we still use this, so we are good
            # Remove this link from iso_md_links to get an overview of which links are left over in the end
            # These links must be new then!
            iso_md_links.remove(xml_link_attr)
            continue
        else:
            # this does not seem to exist anymore -> remove it from the xml
            xml_helper.remove_element(xml_link)
    # what is left over in iso_md_links are new links that must be added to the capabilities doc
    for new_link in iso_md_links:
        xml_helper.add_iso_md_element(xml_obj, new_link)


def _overwrite_capabilities_data(xml_obj: _Element, metadata: Metadata):
    """ Overwrites capabilities document data with changed data from editor based changes.

    Only capable of changing <Title>, <Abstract> and <AccessConstraints>

    Args:
        xml_obj (_Element): The document xml object
        metadata (Metadata): The metadata holding the data
    Returns:

    """

    elements = {
        "Title": metadata.title,
        "Abstract": metadata.abstract,
        "AccessConstraints": metadata.access_constraints,
    }
    for key, val in elements.items():
        try:
            # Check if element exists to change it
            key_xml_obj = xml_helper.try_get_single_element_from_xml("./" + GENERIC_NAMESPACE_TEMPLATE.format(key), xml_obj)
            if key_xml_obj is not None:
                # Element exists, we can change it easily
                xml_helper.write_text_to_element(xml_obj, "./" + GENERIC_NAMESPACE_TEMPLATE.format(key), val)
            else:
                # The element does not exist (happens in case of abstract sometimes)
                # First create, than change it
                xml_helper.create_subelement(xml_obj, key, )
                xml_helper.write_text_to_element(xml_obj, "./" + GENERIC_NAMESPACE_TEMPLATE.format(key), val)
        except AttributeError as e:
            # for not is_root this will fail in AccessConstraints querying
            pass


def overwrite_capabilities_document(metadata: Metadata):
    """ Overwrites the capabilities document which is related to the provided metadata.

    If a subelement of a service has been edited, the service root capabilities will be changed since this is the
    most requested document of the service.
    All subelements capabilities documents above the edited element will be reset to None and cached documents will be
    cleared. This forces an automatic creation of the correct capabilities on the next request for these elements,
    which will result in correct information about the edited subelement.

    Args:
        metadata (Metadata):
    Returns:
         nothing
    """
    is_root = metadata.is_root()
    if is_root:
        parent_metadata = metadata
    elif metadata.is_metadata_type(MetadataEnum.LAYER):
        parent_metadata = metadata.service.parent_service.metadata
    elif metadata.is_metadata_type(MetadataEnum.FEATURETYPE):
        parent_metadata = metadata.featuretype.parent_service.metadata

    # Make sure the Document record already exist by fetching the current capability xml
    # This is a little trick to auto-generate Document records which did not exist before!
    parent_metadata.get_current_capability_xml(parent_metadata.get_service_version().value)
    cap_doc = Document.objects.get(related_metadata=parent_metadata)

    # overwrite all editable data
    identifier = metadata.identifier
    xml_obj_root = xml_helper.parse_xml(cap_doc.current_capability_document)

    # find matching xml element in xml doc
    _type = metadata.get_service_type()
    _version = metadata.get_service_version()

    if is_root:
        if metadata.is_service_type(OGCServiceEnum.WFS):
            if _version is OGCServiceVersionEnum.V_2_0_0 or _version is OGCServiceVersionEnum.V_2_0_2:
                XML_NAMESPACES["wfs"] = "http://www.opengis.net/wfs/2.0"
                XML_NAMESPACES["ows"] = "http://www.opengis.net/ows/1.1"
                XML_NAMESPACES["fes"] = "http://www.opengis.net/fes/2.0"
                XML_NAMESPACES["default"] = XML_NAMESPACES["wfs"]
            identifier = metadata.title

    xml_obj = xml_helper.find_element_where_text(xml_obj_root, txt=identifier)
    if len(xml_obj) > 0:
        xml_obj = xml_obj[0]

    # handle keywords
    _overwrite_capabilities_keywords(xml_obj, metadata, _type)

    # handle iso metadata links
    _overwrite_capabilities_iso_metadata_links(xml_obj, metadata)

    # overwrite data
    _overwrite_capabilities_data(xml_obj, metadata)

    # write xml back to Document record
    xml = xml_helper.xml_to_string(xml_obj_root)
    cap_doc.current_capability_document = xml
    cap_doc.save()

    # Delete all cached documents, which holds old state!
    metadata.clear_cached_documents()

    # Delete all cached documents of root service, which holds old state!
    parent_metadata.clear_cached_documents()

    # Remove existing document contents from upper elements (children of root element), which holds old state!
    metadata.clear_upper_element_capabilities(clear_self_too=True)


@transaction.atomic
def _remove_iso_metadata(metadata: Metadata, md_links: list, existing_iso_links: list):
    """ Remove iso metadata that is not found in the newer md_links list but still lives in the persisted existing_iso_links list

    Args:
        metadata (Metadata): The edited metadata
        md_links (list): The new iso metadata links
        existing_iso_links (list): The existing metadata links, related to the metadata object
    Returns:
         nothing
    """
    # remove iso metadata from capabilities document
    rel_md = metadata
    service_type = metadata.get_service_type()
    if not metadata.is_root():
        if service_type == 'wms':
            rel_md = metadata.service.parent_service.metadata
        elif service_type == 'wfs':
            rel_md = metadata.featuretype.parent_service.metadata
    cap_doc = Document.objects.get(related_metadata=rel_md)
    cap_doc_txt = cap_doc.current_capability_document
    xml_cap_obj = xml_helper.parse_xml(cap_doc_txt).getroot()

    # if there are links in existing_iso_links that do not show up in md_links -> remove them
    for link in existing_iso_links:
        if link not in md_links:
            missing_md = MetadataRelation.objects.get(metadata_from=metadata, metadata_to__metadata_url=link)
            missing_md = missing_md.metadata_to
            missing_md.delete()
            # remove from capabilities
            xml_iso_element = xml_helper.find_element_where_attr(xml_cap_obj, "xlink:href", link)
            for elem in xml_iso_element:
                xml_helper.remove_element(elem)
    cap_doc_txt = xml_helper.xml_to_string(xml_cap_obj)
    cap_doc.current_capability_document = cap_doc_txt
    cap_doc.save()


@transaction.atomic
def _add_iso_metadata(metadata: Metadata, md_links: list, existing_iso_links: list):
    """ Adds iso metadata that is found in the newer md_links list but not in the persisted existing_iso_links list

    Args:
        metadata (Metadata): The edited metadata
        md_links (list): The new iso metadata links
        existing_iso_links (list): The existing metadata links, related to the metadata object
    Returns:
         nothing
    """
    # iterate over all links from the form and check if we need to persist them
    for link in md_links:
        if len(link) == 0:
            continue
        # check if this is already an existing uri and skip if so
        if link in existing_iso_links:
            continue
        # ... otherwise create a new iso metadata object
        iso_md = ISOMetadata(link, "editor")
        iso_md = iso_md.to_db_model(created_by=metadata.created_by)
        iso_md.save()
        md_relation = MetadataRelation()
        md_relation.metadata_from = metadata
        md_relation.metadata_to = iso_md
        md_relation.origin = MetadataOrigin.objects.get_or_create(
                name=iso_md.origin
            )[0]
        md_relation.relation_type = MD_RELATION_TYPE_DESCRIBED_BY
        md_relation.save()


@transaction.atomic
def resolve_iso_metadata_links(request: HttpRequest, metadata: Metadata, editor_form):
    """ Iterate over all provided iso metadata links and create metadata from it which will be related to the metadata

    Args:
        metadata (Metadata): The edited metadata
        editor_form: The editor form
    Returns:
         nothing
    """
    # iterate over iso metadata links and create IsoMetadata objects
    md_links = editor_form.data.get("iso_metadata_url", "").split(",")

    # create list of all persisted and related iso md links
    existing_iso_links = metadata.get_related_metadata_uris()

    try:
        _remove_iso_metadata(metadata, md_links, existing_iso_links)
        _add_iso_metadata(metadata, md_links, existing_iso_links)
    except MissingSchema as e:
        messages.add_message(request, messages.ERROR, EDITOR_INVALID_ISO_LINK.format(e.link))
    except Exception as e:
        messages.add_message(request, messages.ERROR, e)


@transaction.atomic
def overwrite_metadata(original_md: Metadata, custom_md: Metadata, editor_form):
    """ Overwrites the original data with the custom date

    Args:
        original_md (Metadata): The original Metadata object
        custom_md (Metadata): The custom Metadata object
        editor_form: The editor form which holds additional data
    Returns:
        nothing
    """
    original_md.title = custom_md.title
    original_md.abstract = custom_md.abstract
    original_md.access_constraints = custom_md.access_constraints
    original_md.metadata_url = custom_md.metadata_url
    original_md.terms_of_use = custom_md.terms_of_use
    # get db objects from values

    # Keyword updating
    keywords = editor_form.cleaned_data["keywords"]
    original_md.keywords.clear()
    for kw in keywords:
        keyword = Keyword.objects.get_or_create(keyword=kw)[0]
        original_md.keywords.add(keyword)

    # Categories updating
    # Categories are provided as id's to prevent language related conflicts
    categories = editor_form.cleaned_data["categories"]
    original_md.categories.clear()
    for category in categories:
        original_md.categories.add(category)

    # Categories are inherited by subelements
    subelement_mds = original_md.get_subelements_metadatas()
    for subelement_md in subelement_mds:
        subelement_md.categories.clear()
        for category in categories:
            subelement_md.categories.add(category)

    # change capabilities document so that all sensitive elements (links) are proxied
    if original_md.use_proxy_uri != custom_md.use_proxy_uri:
        if custom_md.use_proxy_uri == 'on':
            original_md.set_proxy(True)
        else:
            original_md.set_proxy(False)

    # save metadata
    original_md.is_custom = True
    original_md.save()
    overwrite_capabilities_document(original_md)


def overwrite_featuretype(original_ft: FeatureType, custom_ft: FeatureType, editor_form):
    """ Overwrites the original data with the custom date

    Args:
        original_ft (FeatureType): THe original FeatureType object
        custom_ft (FeatureType): The custom FeatureType object
        editor_form: The editor form which holds additional data
    Returns:
        nothing
    """
    # keywords are provided as usual text
    keywords = editor_form.data.get("keywords").split(",")
    if len(keywords) == 1 and keywords[0] == '':
        keywords = []

    original_ft.title = custom_ft.title
    original_ft.abstract = custom_ft.abstract

    original_ft.keywords.clear()
    for kw in keywords:
        keyword = Keyword.objects.get_or_create(keyword=kw)[0]
        original_ft.keywords.add(keyword)
    original_ft.is_custom = True
    original_ft.save()


def prepare_secured_operations_groups(operations, sec_ops, all_groups, metadata):
    """ Merges RequestOperations and SecuredOperations into a usable form for the template rendering.

    Iterates over all SecuredOperations of a metadata, simplifies the objects into dicts, adds the remaining
    RequestOperation objects.

    Args:
        operations: The RequestOperation query set
        sec_ops: The SecuredOperation query set
        all_groups: All system groups
        metadata: The secured metadata
    Returns:
         A list, containing dicts of all operations with groups and only the most important data
    """
    tmp = []
    for op in operations:
        op_dict = {
            "operation": op,
            "groups": []
        }
        secured_operations = SecuredOperation.objects.filter(
            operation=op,
            secured_metadata=metadata,
        )
        if secured_operations.count() > 0:
            allowed_groups = [x.allowed_group for x in secured_operations]

            for group in all_groups:
                allowed = False
                sec_id = -1
                geometry = None
                if group in allowed_groups:
                    allowed = True
                    sec_op = secured_operations.get(allowed_group=group)
                    geometry_collection = sec_op.bounding_geometry
                    polygon_list = [json.loads(x.geojson) for x in geometry_collection]
                    geometry = json.dumps(polygon_list)
                    if len(polygon_list) == 0:
                        geometry = None
                    sec_id = sec_op.id

                op_dict["groups"].append({
                    "group": group,
                    "allowed": allowed,
                    "sec_id": sec_id,
                    "geo_json_geometry": geometry,
                })

            tmp.append(op_dict)

        else:
            for group in all_groups:
                op_dict["groups"].append({
                    "group": group,
                    "allowed": False,
                    "sec_id": -1,
                    "geo_json_geometry": None,
                })
            tmp.append(op_dict)
    return tmp
