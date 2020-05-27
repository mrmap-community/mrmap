"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 26.05.20

This file defines some xml skeletons for the ISO 19115 standard for now.
"""
NS_GCO = "gco"
NS_GMD = "gmd"


def create_xml_doc(content: str, encoding: str = "utf-8", xml_version: str = "1.0"):
    return f"<?xml version=\"{xml_version}\" encoding=\"{encoding}\"?>{content}"


def create_xml_element(tag_name: str, content: str, ns: str = None, attributes: {} = None, ):
    """
        Mandatory Keywords:
            tag_name: the name of the xml element
            content: the content of the xml element

        Optional Keywords:
            ns: the namespace of the xml element
            attributes: the attributes of the xml element

        Returns:
            <ns:tag_name list(attributes)>content</ns:tag_name>
    """
    attrs = ""
    if attributes is not None:
        for key, value in attributes.items():
            attrs += f" {key}={value}"

    return f"<{tag_name}{attrs}>{content}</{tag_name}>" if ns is None else f"<{ns}:{tag_name}{attrs}>{content}</{ns}:{tag_name}>"


def create_gco_character_string(string: str):
    """
        Mandatory Keywords:
            string: the content of the xml element

        Returns:
            gmd:CharacterString xml element
    """
    return create_xml_element(ns=NS_GCO, tag_name="CharacterString", content=string)
