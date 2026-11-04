"""Declarative access and coupling extraction for ISO 19139 records (#981).

These are the access and coupling elements epic #669 finds endpoint and
coupling evidence in. They are mapped as `_values` specs: the mapper reads
them with the same traversal, namespace machinery and XPath interpretation as
every other field, but they have no model and no persistence of their own -
the mapped document carries them as ordered lists of plain dicts with the
original external values, and `XmlMapper.mapped_values()` answers them without
a PersistenceHandler (#983 adds the models and persistence on top of this).

Sharing the specs between the record configs keeps one XPath interpretation of
`onLine` for all of them; `ApplicationConfigDriftGuardTest` relies on dataset
and application answering the identical spec.
"""

# the CI_OnlineResource element of a distribution transfer option; a service
# record keeps its advertised links in the same distributionInfo shape as a
# dataset record does
ONLINE_LINKS = {
    "_values": True,
    "_base_xpath": "./gmd:distributionInfo/gmd:MD_Distribution/gmd:transferOptions/gmd:MD_DigitalTransferOptions/gmd:onLine/gmd:CI_OnlineResource",
    "fields": {
        # gmd:URL is the classic encoding of gmd:linkage, gco:CharacterString
        # the one the INSPIRE distribution rules allow - both carry the URL
        "linkage": "./gmd:linkage/*[self::gmd:URL or self::gco:CharacterString]",
        # gmx:Anchor names the protocol by its definition URI and shows a
        # label; the anchor href is the external value worth keeping
        "protocol": "./gmd:protocol/gco:CharacterString | ./gmd:protocol/gmx:Anchor/@xlink:href",
        "application_profile": "./gmd:applicationProfile/gco:CharacterString | ./gmd:applicationProfile/gmx:Anchor/@xlink:href",
        "name": "./gmd:name/gco:CharacterString",
        "description": "./gmd:description/gco:CharacterString",
        # the codeListValue is the machine value of CI_OnLineFunctionCode;
        # records that do not use the code list spell the function out as text
        "function": "./gmd:function/gmd:CI_OnLineFunctionCode/@codeListValue | ./gmd:function/gco:CharacterString",
    },
}

# the same links a distributor advertises alongside the distribution itself
DISTRIBUTOR_ONLINE_LINKS = {
    **ONLINE_LINKS,
    "_base_xpath": "./gmd:distributionInfo/gmd:MD_Distribution/gmd:distributor/gmd:MD_Distributor/gmd:distributorTransferOptions/gmd:MD_DigitalTransferOptions/gmd:onLine/gmd:CI_OnlineResource",
}

# the operations a service identification advertises, with the endpoint each
# of them is reached at
SERVICE_OPERATIONS = {
    "_values": True,
    "_base_xpath": "./gmd:identificationInfo/srv:SV_ServiceIdentification/srv:containsOperations/srv:SV_OperationMetadata",
    "fields": {
        "operation_name": "./srv:operationName/gco:CharacterString",
        # srv:DCPList names the transfer protocol by codeListValue, records
        # may also spell it out as a character string
        "dcp": "./srv:DCP/srv:DCPList/@codeListValue | ./srv:DCP/gco:CharacterString",
        "connect_point_linkage": "./srv:connectPoint/gmd:CI_OnlineResource/gmd:linkage/*[self::gmd:URL or self::gco:CharacterString]",
    },
}

# the metadata records a service declares to operate on: uuidref names the
# record, href points at it - two evidence strands, kept apart as the document
# carries them (#982 defines how they resolve; #669 forbids comparing them
# as one identifier blindly)
OPERATES_ON = {
    "_values": True,
    "_base_xpath": "./gmd:identificationInfo/srv:SV_ServiceIdentification/srv:operatesOn",
    "fields": {
        "uuidref": "./@uuidref",
        "href": "./@xlink:href",
    },
}

# the SV_CoupledResource entries binding an operation to a resource of the
# operated-on record
COUPLED_RESOURCES = {
    "_values": True,
    "_base_xpath": "./gmd:identificationInfo/srv:SV_ServiceIdentification/srv:coupledResource/srv:SV_CoupledResource",
    "fields": {
        "identifier": "./srv:identifier/gco:CharacterString",
        "operation_name": "./srv:operationName/gco:CharacterString",
        # gco:LocalName is the typed name, gco:CharacterString the plain one
        "scoped_name": "./srv:scopedName/*[self::gco:LocalName or self::gco:CharacterString]",
    },
}
