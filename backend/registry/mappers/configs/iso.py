from registry.mappers.namespaces import (GCO_NAMESPACE, GMD_NAMESPACE,
                                         SRV_NAMESPACE)

XPATH_MAP = {
    ("ISO", "Dataset"): {
        "_namespaces": {
            "gmd": GMD_NAMESPACE,
            "gco": GCO_NAMESPACE,
            "srv": SRV_NAMESPACE,
        },
        "_schema": "http://www.isotc211.org/2005/gmd",
        "_pre_save": [
        ],
        "dataset": {
            "_model": "registry.DatasetMetadataRecord",
            "_base_xpath": "/gmd:MD_Metadata",
            "fields": {
                "title": "./gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString",
                "abstract": "./gmd:abstract/gco:CharacterString",
                "access_constraints": "./gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:accessConstraints/gmd:MD_RestrictionCode/@codeListValue=\"otherRestrictions\"]/gmd:otherConstraints/gco:CharacterString",
                "code": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:MD_Identifier/gmd:code/gco:CharacterString | ./gmd:identificationInfo/srv:SV_ServiceIdentification",
                "code_space": "",
                "date_stamp": {
                    "_inputs": ("./gmd:dateStamp/*[self::gco:DateTime or self::gco:Date]/text()",),
                    "_parser": "registry.mappers.parsers.value.string_to_datetime",
                },
                "bounding_geometry": "",
                "spatial_res_type": "",
                "spatial_res_value": "",
                "file_identifier": "./gmd:fileIdentifier/gco:CharacterString",
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "./gmd:descriptiveKeywords/gmd:MD_Keywords/gmd:keyword",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "keyword": "./gco:CharacterString"
                    }
                },
                "dataset_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./gmd:pointOfContact/gmd:CI_ResponsibleParty",
                    "_create_mode": "get_or_create",
                    "fields": {
                        "name": "./gmd:organisationName/gco:CharacterString",
                        "person_name": "./gmd:individualName/gco:CharacterString",
                        "phone": "./gmd:contactInfo/gmd:CI_Contact/gmd:phone/gmd:CI_Telephone/gmd:voice/gco:CharacterString",
                        "email": "./gmd:contactInfo/gmd:CI_Contact/gmd:address/gmd:CI_Address/gmd:electronicMailAddress/gco:CharacterString",
                    }
                },
                "metadata_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./gmd:contact/gmd:CI_ResponsibleParty",
                    "_create_mode": "get_or_create",
                    "fields": {
                        "name": "./gmd:organisationName/gco:CharacterString",
                        "person_name": "./gmd:individualName/gco:CharacterString",
                        "phone": "./gmd:contactInfo/gmd:CI_Contact/gmd:phone/gmd:CI_Telephone/gmd:voice/gco:CharacterString",
                        "email": "./gmd:contactInfo/gmd:CI_Contact/gmd:address/gmd:CI_Address/gmd:electronicMailAddress/gco:CharacterString",
                    }
                },
                "reference_systems": {
                    "_model": "registry.ReferenceSystem",
                    "_base_xpath": "./gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "_parser": "registry.mappers.parsers.wfs.parse_reference_systems",
                },
            }
        }
    },
}
