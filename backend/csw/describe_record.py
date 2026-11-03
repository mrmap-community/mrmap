"""The DescribeRecordResponse of the /csw endpoint (#907).

DescribeRecord is mandatory for a CSW 2.0.2 catalogue (OGC 07-006r1, Table 60)
and answers the schema of the record types the catalogue serves. MrMap serves
one type: ``gmd:MD_Metadata``, the type GetCapabilities advertises as typeNames
and whose stored documents every GetRecords returns. MrMap keeps no copy of the
ISO 19139 schema and redeclaring its components would collide with the schema a
client loads beside this description, so the answer is the SchemaComponent of
Table 13 which *references* that schema instead of duplicating it: an
``xs:schema`` fragment of the gmd target namespace which includes the schema at
its normative location, with a documentation that names what it describes. That
is the schema description this catalogue can defensibly answer with, and the
sibling response builders in ``registry/ows_lib/csw/builder.py`` stay untouched.
"""

from lxml import etree
from registry.ows_lib.xml.builder import XS_NS, XSDSkeletonBuilder
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

# Table 13 of OGC 07-006r1 registers this URI as the schemaLanguage the response
# defaults to; it names a schema language and is never requested over the
# network, so the insecure transport finding on it is a false positive.
XML_SCHEMA_LANGUAGE = "http://www.w3.org/XML/Schema"  # NOSONAR normative W3C XML Schema language identifier, echoed into the response - not a network endpoint

# Where ISO 19139 publishes the schema of gmd:MD_Metadata. DescribeRecord echoes
# this location to the client (issue #907's suggested fix: "e.g. by echoing the
# ISO 19139 schema location"); mrmap never requests it.
GMD_SCHEMA_LOCATION = "http://www.isotc211.org/2005/gmd/gmd.xsd"  # NOSONAR normative ISO 19139 schema location, echoed to the client - not a network endpoint

# Which SchemaComponent answers which advertised typeName; the one type this
# catalogue knows is the ISO 19139 record every GetRecords answers.
SCHEMA_DESCRIPTIONS = {
    "gmd:MD_Metadata": {
        "targetNamespace": NAMESPACE_LOOKUP["gmd"],
        "parentSchema": GMD_SCHEMA_LOCATION,
        "documentation": (
            "The ISO 19139:2007 XML schema of gmd:MD_Metadata, the record "
            "type whose documents this catalogue searches and answers. The "
            "schema is published at the location the xs:include of this "
            "fragment names; mrmap keeps no copy of it and references it "
            "instead of redeclaring its components."
        ),
    },
}

SUPPORTED_RECORD_TYPE_NAMES = tuple(SCHEMA_DESCRIPTIONS)


class CSWDescribeRecordBuilder(XSDSkeletonBuilder):
    """Builds the DescribeRecordResponse on the cswDiscovery skeleton.

    A sibling of ``registry.ows_lib.csw.builder.CSWBuilder`` which lives in the
    csw app, the app that owns this operation; it adds no method to that shared
    builder so the GetRecords builders it carries are not touched.
    """

    def __init__(self, service_version="2.0.2"):
        super().__init__(("csw", "discovery", service_version))
        self.service_version = service_version

    def build_describe_record_response(self, type_names):
        """One SchemaComponent per requested typeName, in the request order.

        :param type_names: typeNames to describe; the caller has screened them
            against :data:`SUPPORTED_RECORD_TYPE_NAMES` -- a name this builder
            has no schema description for is a wiring error, not a client error.
        """
        descriptions = []
        for type_name in type_names:
            description = SCHEMA_DESCRIPTIONS.get(type_name)
            if description is None:
                raise ValueError(
                    f"no schema description registered for typeName {type_name}")
            descriptions.append(description)

        root = self.build_element(
            "DescribeRecordResponse",
            nsmap={
                "csw": NAMESPACE_LOOKUP["csw_2_0_2"],
                "ows": NAMESPACE_LOOKUP["ows"],
                "ogc": NAMESPACE_LOOKUP["ogc"],
                "xlink": NAMESPACE_LOOKUP["xlink"],
                "xs": XS_NS,
                "xsi": NAMESPACE_LOOKUP["xsi"],
            },
            attributes={
                "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation":
                    "http://www.opengis.net/cat/csw/2.0.2 http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd"
            },
            children_attributes={
                "SchemaComponent": [
                    {
                        "_attributes": {
                            "targetNamespace": description["targetNamespace"],
                            "schemaLanguage": XML_SCHEMA_LANGUAGE,
                            "parentSchema": description["parentSchema"],
                        }
                    }
                    for description in descriptions
                ]
            }
        )

        for component, description in zip(
            root.findall(f"{{{NAMESPACE_LOOKUP['csw_2_0_2']}}}SchemaComponent"),
            descriptions
        ):
            self._add_schema_fragment(component, description)

        return root

    def _add_schema_fragment(self, component, description):
        """Adds the Table 13 content of a SchemaComponent: an xs:schema which
        references the schema it describes and carries the documentation which
        names it."""
        schema = etree.SubElement(component, etree.QName(XS_NS, "schema"))
        schema.set("targetNamespace", description["targetNamespace"])
        schema.set("elementFormDefault", "qualified")
        schema.set("attributeFormDefault", "unqualified")

        documentation = etree.SubElement(
            etree.SubElement(schema, etree.QName(XS_NS, "annotation")),
            etree.QName(XS_NS, "documentation"),
        )
        documentation.set("{http://www.w3.org/XML/1998/namespace}lang", "en")
        documentation.text = description["documentation"]

        include = etree.SubElement(schema, etree.QName(XS_NS, "include"))
        include.set("schemaLocation", description["parentSchema"])
