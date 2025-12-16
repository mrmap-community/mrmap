from registry.mappers.namespaces import (GCO_NAMESPACE, GMD_NAMESPACE, GML_3_2_2_NAMESPACE,
                                         SRV_NAMESPACE)

XPATH_MAP = {
    ("ISO", "dataset"): {
        "_namespaces": {
            "gmd": GMD_NAMESPACE,
            "gml": GML_3_2_2_NAMESPACE,
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
                "charset": {
                    "_inputs": ("./gmd:characterSet/gmd:MD_CharacterSetCode/@codeListValue",),
                    "_parser": "registry.mappers.parsers.value.charset_to_enum",
                },
                "update_frequency_code": {
                    "_inputs": ("./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:resourceMaintenance/gmd:MD_MaintenanceInformation/gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode/@codeListValue",),
                    "_parser": "registry.mappers.parsers.value.update_frequency_code_to_enum"
                },
                "language": {
                    "_inputs": ("./gmd:language/gmd:LanguageCode/@codeListValue",),
                    "_parser": "registry.mappers.parsers.value.language_to_enum",
                },
                "title": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString",
                "abstract": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:abstract/gco:CharacterString",
                "access_constraints": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:accessConstraints/gmd:MD_RestrictionCode/@codeListValue=\"otherRestrictions\"]/gmd:otherConstraints/gco:CharacterString",
                "date_stamp": {
                    "_inputs": ("./gmd:dateStamp/*[self::gco:DateTime or self::gco:Date]/text()",),
                    "_parser": "registry.mappers.parsers.value.string_to_datetime",
                },
                "file_identifier": "./gmd:fileIdentifier/gco:CharacterString",
                "bounding_geometry": {
                    "_inputs": (
                        "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:extent/gmd:EX_Extent/gmd:geographicElement/*[self::gmd:EX_GeographicBoundingBox or self::gmd:EX_BoundingPolygon]",),
                    "_parser": "registry.mappers.parsers.value.iso_bbox_to_multipolygon"
                },
                "code": {
                    "_inputs": (
                        "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:MD_Identifier/gmd:code/gco:CharacterString/text()",
                    ),
                    "_parser": "registry.mappers.parsers.value.string_to_code",
                },
                "code_space": {
                    "_inputs": (
                        "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:MD_Identifier/gmd:code/gco:CharacterString/text()",
                    ),
                    "_parser": "registry.mappers.parsers.value.string_to_code_space",
                },
                "equivalent_scale": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:spatialResolution/gmd:MD_Resolution/gmd:equivalentScale/gmd:MD_RepresentativeFraction/gmd:denominator/gco:Integer",
                "ground_res": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:spatialResolution/gmd:MD_Resolution/gmd:distance/gmd:Distance",
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:descriptiveKeywords/gmd:MD_Keywords/gmd:keyword/gco:CharacterString",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "keyword": "./."
                    }
                },
                "dataset_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:pointOfContact/gmd:CI_ResponsibleParty",
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
                    "_base_xpath": "./gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier/gmd:code/gco:CharacterString",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "code": {
                           "_inputs": ("./text()",),
                            "_parser": "registry.mappers.parsers.iso.parse_code",
                        },
                        "prefix": {
                           "_inputs": ("./text()",),
                            "_parser": "registry.mappers.parsers.iso.parse_prefix",
                        },
                    },
                },
                "categories": {
                   "_model": "registry.Category",
                    "_base_xpath": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:topicCategory/gmd:MD_TopicCategoryCode",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "category": {
                            "_inputs": ("./.",), 
                            "_parser": "registry.mappers.parsers.value.topic_category_to_enum",
                        }
                    }
                },
                "time_extents": {
                    "_model": "registry.TimeExtent",
                    "_base_xpath": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "_parser": "registry.mappers.parsers.iso.parse_timeextent",
                },
            }
        }
    },
}
