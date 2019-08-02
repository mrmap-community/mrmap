"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 01.08.19

"""
from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest
from requests.exceptions import MissingSchema

from MapSkinner.messages import EDITOR_INVALID_ISO_LINK
from service.helper.iso.isoMetadata import ISOMetadata
from service.models import Metadata, Keyword, Category, FeatureType, CapabilityDocument, MetadataRelation, \
    MetadataOrigin
from service.helper import xml_helper


def overwrite_capabilities_document(metadata: Metadata):
    """ Overwrites the capabilities document which is related to the provided metadata

    Args:
        metadata (Metadata):
    Returns:
         nothing
    """
    cap_doc = CapabilityDocument.objects.get(related_metadata=metadata)
    # overwrite all editable data
    identifier = metadata.identifier
    xml_obj_root = xml_helper.parse_xml(cap_doc.current_capability_document)

    # find matching xml element in xml doc
    xml_obj = xml_helper.try_get_single_element_from_xml("//Service/Name[text()='{}']/parent::*".format(identifier), xml_obj_root)
    # overwrite data
    elements = {
        "Title": metadata.title,
        "Abstract": metadata.abstract,
        "AccessConstraints": metadata.access_constraints,
    }
    for key, val in elements.items():
        xml_helper.write_text_to_element(xml_obj, "./{}".format(key), val)

    # handle keywords
    xml_keywords_objs = xml_helper.try_get_element_from_xml("./KeywordList/Keyword", xml_obj)
    xml_keywords_list_obj = xml_helper.try_get_single_element_from_xml("./KeywordList", xml_obj)
    # first remove all current keywords
    for kw in xml_keywords_objs:
        xml_keywords_list_obj.remove(kw)
    # then add all current
    for kw in metadata.keywords.all():
        xml_keyword = xml_helper.add_subelement(xml_keywords_list_obj, "Keyword")
        xml_helper.write_text_to_element(xml_keyword, txt=kw.keyword)

    # write xml back to database
    xml = xml_helper.xml_to_string(xml_obj_root)
    cap_doc.current_capability_document = xml
    cap_doc.save()


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
    cap_doc = CapabilityDocument.objects.get(related_metadata=metadata)
    cap_doc_txt = cap_doc.current_capability_document
    xml_cap_obj = xml_helper.parse_xml(cap_doc_txt).getroot()

    # if there are links in existing_iso_links that do not show up in md_links -> remove them
    for link in existing_iso_links:
        if link not in md_links:
            missing_md = MetadataRelation.objects.get(metadata_1=metadata, metadata_2__metadata_url=link)
            missing_md = missing_md.metadata_2
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
        iso_md = iso_md.get_db_model()
        iso_md.save()
        md_relation = MetadataRelation()
        md_relation.metadata_1 = metadata
        md_relation.metadata_2 = iso_md
        md_relation.origin = MetadataOrigin.objects.get_or_create(
                name=iso_md.origin
            )[0]
        md_relation.save()
        metadata.related_metadata.add(md_relation)


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
    existing_iso_mds = metadata.related_metadata.all()
    existing_iso_links = []
    for existing_iso_md in existing_iso_mds:
        existing_iso_links.append(existing_iso_md.metadata_2.metadata_url)

    try:
        _remove_iso_metadata(metadata, md_links, existing_iso_links)
        _add_iso_metadata(metadata, md_links, existing_iso_links)
    except MissingSchema as e:
        messages.add_message(request, messages.ERROR, EDITOR_INVALID_ISO_LINK.format(e.link))
    except Exception as e:
        messages.add_message(request, messages.ERROR, e)


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
    # keywords are provided as usual text
    keywords = editor_form.data.get("keywords").split(",")
    if len(keywords) == 1 and keywords[0] == '':
        keywords = []
    # categories are provided as id's to prevent language related conflicts
    category_ids = editor_form.data.get("categories").split(",")
    if len(category_ids) == 1 and category_ids[0] == '':
        category_ids = []
    original_md.keywords.clear()
    for kw in keywords:
        keyword = Keyword.objects.get_or_create(keyword=kw)[0]
        original_md.keywords.add(keyword)
    for id in category_ids:
        category = Category.objects.get(id=id)
        original_md.categories.add(category)
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