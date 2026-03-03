from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

XPATH_MAP = {
    ("ISO", "dataset"): {
        "_namespaces": {
            "gmd": NAMESPACE_LOOKUP["gmd"],
            "gml": NAMESPACE_LOOKUP["gml_3_2_2"],
            "gco": NAMESPACE_LOOKUP["gco"],
            "srv": NAMESPACE_LOOKUP["srv"],
        },
        "_schema": "http://www.isotc211.org/2005/gmd",
        "_pre_save": [
        ],
        "dataset": {
            "_model": "registry.DatasetMetadataRecord",
            "_base_xpath": "/gmd:MD_Metadata",
            "_create_mode": "registry.mappers.persistence.custom.get_or_create_metadatarecord",
            "fields": {
                "charset": {
                    "_inputs": ("./gmd:characterSet/gmd:MD_CharacterSetCode[@codeList='http://wis.wmo.int/2011/schemata/iso19139_2007/schema/resources/Codelist/ML_gmxCodelists.xml#MD_CharacterSetCode']/@codeListValue",),
                    "_parser": "registry.mappers.parsers.value.charset_to_enum",
                    # TODO: "_reverse_parser": "",
                },
                "update_frequency_code": {
                    "_inputs": ("./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:resourceMaintenance/gmd:MD_MaintenanceInformation/gmd:maintenanceAndUpdateFrequency/gmd:MD_MaintenanceFrequencyCode/@codeListValue",),
                    "_parser": "registry.mappers.parsers.value.update_frequency_code_to_enum"
                    # TODO: "_reverse_parser": "",
                },
                "title": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString",
                "abstract": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:abstract/gco:CharacterString",
                "access_constraints": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:accessConstraints/gmd:MD_RestrictionCode/@codeListValue=\"otherRestrictions\"]/gmd:otherConstraints/gco:CharacterString",
                "date_stamp": {
                    "_inputs": ("./gmd:dateStamp/*[self::gco:DateTime or self::gco:Date]/text()",),
                    "_parser": "registry.mappers.parsers.value.string_to_datetime",
                    # TODO: "_reverse_parser": "",
                },
                "file_identifier": "./gmd:fileIdentifier/gco:CharacterString",
                "bounding_geometry": {
                    "_inputs": (
                        "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:extent/gmd:EX_Extent/gmd:geographicElement/*[self::gmd:EX_GeographicBoundingBox or self::gmd:EX_BoundingPolygon]",),
                    "_parser": "registry.mappers.parsers.value.iso_bbox_to_multipolygon"
                    # TODO: "_reverse_parser": "",
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
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:descriptiveKeywords/gmd:MD_Keywords/gmd:keyword/gco:CharacterString[text()='{keyword}']",
                        },
                    },
                    "fields": {
                        "keyword": "./."
                    }
                },
                "dataset_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:pointOfContact/gmd:CI_ResponsibleParty",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:pointOfContact/gmd:CI_ResponsibleParty",
                        },
                    },
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
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./gmd:contact/gmd:CI_ResponsibleParty",
                        },
                    },
                    "fields": {
                        "name": "./gmd:organisationName/gco:CharacterString",
                        "person_name": "./gmd:individualName/gco:CharacterString",
                        "phone": "./gmd:contactInfo/gmd:CI_Contact/gmd:phone/gmd:CI_Telephone/gmd:voice/gco:CharacterString",
                        "email": "./gmd:contactInfo/gmd:CI_Contact/gmd:address/gmd:CI_Address/gmd:electronicMailAddress/gco:CharacterString",
                    }
                },
                "languages": {
                    "_model": "registry.Language",
                    "_base_xpath": "./gmd:language/gmd:LanguageCode[@codeList='http://www.loc.gov/standards/iso639-2/']",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "compiler": "registry.mappers.identifiers.language_identifier",
                        },
                    },
                    "fields": {
                        "value": {
                            "_inputs": ("./@codeListValue",),
                            "_parser": "registry.mappers.parsers.value.language_to_enum",
                            "_reverse_parser": "registry.mappers.parsers.value.int_to_language"
                        }
                    }
                },
                "reference_systems": {
                    "_model": "registry.ReferenceSystem",
                    "_base_xpath": "./gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier/gmd:code/gco:CharacterString",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "compiler": "registry.mappers.identifiers.refence_system_identifier",
                        },
                    },
                    "_parser": "registry.mappers.parsers.iso.parse_reference_system",
                    "_reverse_parser": "registry.mappers.parsers.iso.serialize_reference_system",
                },
                "categories": {
                    "_model": "registry.IsoCategory",
                    "_base_xpath": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:topicCategory/gmd:MD_TopicCategoryCode",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "compiler": "registry.mappers.identifiers.category_identifier",
                        },
                    },
                    "_parser": "registry.mappers.parsers.iso.parse_topic_category",
                    "_reverse_parser": "registry.mappers.parsers.iso.serialize_topic_category",
                },
                "time_extents": {
                    "_model": "registry.TimeExtent",
                    "_base_xpath": "./gmd:identificationInfo/gmd:MD_DataIdentification/gmd:extent/gmd:EX_Extent/gmd:temporalElement/gmd:EX_TemporalExtent/gmd:extent",
                    "_create_mode": "get_or_create",
                    "_parser": "registry.mappers.parsers.iso.parse_timeextent",
                    # TODO: "__reverse_parser": "",
                    "_reverse": {
                        "_identifier": {
                            "compiler": "registry.mappers.identifiers.timeextent_identifier",
                        },
                    },
                },
            }
        }
    },
}
