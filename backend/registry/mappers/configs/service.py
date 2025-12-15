from registry.mappers.namespaces import (GCO_NAMESPACE, GMD_NAMESPACE, GML_3_2_2_NAMESPACE,
                                         GMX_NAMESPACE, SRV_NAMESPACE,
                                         XLINK_NAMESPACE)

XPATH_MAP = {
    ("ISO", "service"): {
        "_namespaces": {
            "gmd": GMD_NAMESPACE,
            "gco": GCO_NAMESPACE,
            "gml": GML_3_2_2_NAMESPACE,
            "gmx": GMX_NAMESPACE,
            "srv": SRV_NAMESPACE,
            "xlink": XLINK_NAMESPACE,
        },
        "_schema": "http://www.isotc211.org/2005/gmd",
        "_pre_save": [
        ],
        "dataset": {
            "_model": "registry.ServiceMetadataRecord",
            "_base_xpath": "/gmd:MD_Metadata",
            "fields": {
                "charset": {
                    "_inputs": ("./gmd:characterSet/gmd:MD_CharacterSetCode/@codeListValue",),
                    "_parser": "registry.mappers.parsers.value.charset_to_enum",
                },
                "update_frequency_code": {
                    "_inputs": ("./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:resourceMaintenance/gmd:MD_MaintenanceInformation/gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode/@codeListValue",),
                    "_parser": "registry.mappers.parsers.value.update_frequency_code_to_enum"
                },
                "language": {
                    "_inputs": ("./gmd:language/gmd:LanguageCode/@codeListValue",),
                    "_parser": "registry.mappers.parsers.value.language_to_enum",
                },
                "title": "./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString",
                "abstract": "./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:abstract/gco:CharacterString",
                "access_constraints": "./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:accessConstraints/gmd:MD_RestrictionCode/@codeListValue=\"otherRestrictions\"]/gmd:otherConstraints/gco:CharacterString",
                "date_stamp": {
                    "_inputs": ("./gmd:dateStamp/*[self::gco:DateTime or self::gco:Date]/text()",),
                    "_parser": "registry.mappers.parsers.value.string_to_datetime",
                },
                "file_identifier": "./gmd:fileIdentifier/gco:CharacterString",
                "bounding_geometry": {
                    "_inputs": (
                        "./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:extent/gmd:EX_Extent/gmd:geographicElement/*[self::gmd:EX_GeographicBoundingBox or self::gmd:EX_BoundingPolygon]",),
                    "_parser": "registry.mappers.parsers.value.iso_bbox_to_multipolygon"
                },

                "equivalent_scale": "./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:spatialResolution/gmd:MD_Resolution/gmd:equivalentScale/gmd:MD_RepresentativeFraction/gmd:denominator/gco:Integer",
                "ground_res": "./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:spatialResolution/gmd:MD_Resolution/gmd:distance/gmd:Distance",
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:descriptiveKeywords/gmd:MD_Keywords/gmd:keyword/gco:CharacterString",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "keyword": "./."
                    }
                },
                "metadata_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:pointOfContact/gmd:CI_ResponsibleParty",
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
                    "_base_xpath": "./gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier/gmd:code/gmx:Anchor",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "code": {
                           "_inputs": ("./@xlink:href",),
                            "_parser": "registry.mappers.parsers.iso.parse_code",
                        },
                        "prefix": {
                           "_inputs": ("./@xlink:href",),
                            "_parser": "registry.mappers.parsers.iso.parse_prefix",
                        },
                    },
                },
                # TODO
                # "categories": {
                #    "_model": "registry.Category",
                #     "_base_xpath": "./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:topicCategory/gmd:MD_TopicCategoryCode",

                # },
                # TODO
                # "time_extents": {
                #     "_model": "registry.TimeExtent",
                #     "_base_xpath": "./gmd:identificationInfo/srv:SV_ServiceIdentification/srv:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent | ./gmd:identificationInfo/srv:SV_ServiceIdentification/gmd:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent",
                #     "_create_mode": "get_or_create",
                #     "_many": True,
                #     "_parser": "registry.mappers.parsers.wms.parse_timeextent",
                # },
            }
        }
    },
}
