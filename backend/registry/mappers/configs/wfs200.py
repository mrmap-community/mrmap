from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

XPATH_MAP = {
    # (Service-Klasse, Version) -> Mapping Feldname -> XPath
    ("WFS", "2.0.0"): {
        "_namespaces": {
            "xlink": NAMESPACE_LOOKUP["xlink"],
            "wfs": NAMESPACE_LOOKUP["wfs_2_0_0"],
            "ows": NAMESPACE_LOOKUP["ows_1_1"],
            "gml": NAMESPACE_LOOKUP["gml_3_2_2"],
            "fes": NAMESPACE_LOOKUP["fes_2_0"],
            "inspire_common": NAMESPACE_LOOKUP["inspire_common"],
        },
        "_schema": "http://www.opengis.net/wfs/2.0",
        "_pre_save": [
            "registry.mappers.extensions.clean_up_operation_urls"
        ],
        "service": {
            "_model": "registry.WebFeatureService",
            "_base_xpath": "/wfs:WFS_Capabilities",
            "fields": {
                "version":  {
                    "_inputs": ("./@version",),
                    "_parser": "registry.mappers.parsers.value.version_to_int",
                    "_reverse_parser": "registry.mappers.parsers.value.int_to_version"
                },
                "title": "./ows:ServiceIdentification/ows:Title",
                "abstract": "./ows:ServiceIdentification/ows:Abstract",
                "fees": "./ows:ServiceIdentification/ows:Fees",
                "access_constraints": "./ows:ServiceIdentification/ows:AccessConstraints",
                "remote_metadata": {
                    "_model": "registry.WebFeatureServiceRemoteMetadata",
                    "_base_xpath": "./ows:OperationsMetadata/ows:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./ows:OperationsMetadata/ows:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL/[text()='{link}']",
                        },
                    },
                    "fields": {
                        "link": "./."
                    }
                },
                "service_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./ows:ServiceProvider",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./ows:ServiceProvider",
                        },
                    },
                    "fields": {
                        "name": "./ows:ProviderName",
                        "person_name": "./ows:ServiceContact/ows:IndividualName",
                        "phone": "./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Voice",
                        "facsimile": "./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Facsimile",
                        "email": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:ElectronicMailAddress",
                        "country": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:Country",
                        "postal_code": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:PostalCode",
                        "city": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:City",
                        "state_or_province": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:AdministrativeArea",
                        "address": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:DeliveryPoint"
                    }
                },
                "metadata_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./ows:ServiceProvider",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./ows:ServiceProvider",
                        },
                    },
                    "fields": {
                        "name": "./ows:ProviderName",
                        "person_name": "./ows:ServiceContact/ows:IndividualName",
                        "phone": "./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Voice",
                        "facsimile": "./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Facsimile",
                        "email": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:ElectronicMailAddress",
                        "country": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:Country",
                        "postal_code": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:PostalCode",
                        "city": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:City",
                        "state_or_province": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:AdministrativeArea",
                        "address": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:DeliveryPoint"
                    }
                },
                "operation_urls": {
                    "_model": "registry.WebFeatureServiceOperationUrl",
                    "_base_xpath": "./ows:OperationsMetadata/ows:Operation/ows:DCP/ows:HTTP//*[self::ows:Post or self::ows:Get]",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "compiler": "registry.mappers.identifiers.wfs_operation_url_identifier"
                        },
                    },
                    "fields": {
                        "method": {
                            "_inputs": (".",),
                            "_parser": "registry.mappers.parsers.value.method_to_enum",
                            "_reverse_parser": "registry.mappers.parsers.value.serialize_method",
                        },
                        "operation": {
                            "_inputs": ("../../../@name",),
                            "_parser": "registry.mappers.parsers.value.operation_to_enum",
                            "_reverse_parser": "registry.mappers.parsers.value.serialize_operation"
                        },
                        "url": "./@xlink:href",
                        "mime_types": {
                            "_model": "registry.MimeType",
                            "_base_xpath": '../../../ows:Parameter[@name="outputFormat"]/ows:Value',
                            "_create_mode": "get_or_create",
                            "fields": {
                                "mime_type": "."
                            }
                        }
                    },
                },
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "./ows:ServiceIdentification/ows:Keywords/ows:Keyword",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./ows:ServiceIdentification/ows:Keywords/ows:Keyword[text()='{keyword}']",
                        },
                    },
                    "fields": {
                        "keyword": "./."
                    }
                },
                "featuretypes": {
                    "_model": "registry.FeatureType",
                    "_base_xpath": "./wfs:FeatureTypeList/wfs:FeatureType",
                    "_create_mode": "bulk",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./wfs:FeatureTypeList/wfs:FeatureType[wfs:Name='{identifier}']",
                        },
                    },
                    "fields": {
                        "identifier": "./wfs:Name",
                        "title": "./wfs:Title",
                        "abstract": "./wfs:Abstract",
                        "bbox_lat_lon": {
                            "_inputs": (
                                "./ows:WGS84BoundingBox/ows:LowerCorner/text()",
                                "./ows:WGS84BoundingBox/ows:UpperCorner/text()"),
                            "_parser": "registry.mappers.parsers.wfs.bbox_to_polygon",
                            "_reverse_parser": "registry.mappers.parsers.wfs.polygon_to_bbox"
                        },
                        "keywords": {
                            "_model": "registry.Keyword",
                            "_base_xpath": "./ows:Keywords/ows:Keyword",
                            "_create_mode": "get_or_create",
                            "_reverse": {
                                "_identifier": {
                                    "xpath": "./ows:Keywords/ows:Keyword[text()='{keyword}']",
                                },
                            },
                            "fields": {
                                "keyword": "./."
                            }
                        },
                        "output_formats": {
                            "_model": "registry.MimeType",
                            "_base_xpath": "./wfs:OutputFormats/wfs:Format",
                            "_create_mode": "get_or_create",
                            "_reverse": {
                                "_identifier": {
                                    "xpath": "./wfs:OutputFormats/wfs:Format[text()='{mime_type}']",
                                },
                            },
                            "fields": {
                                "mime_type": "./."
                            }
                        },
                        "default_reference_system": {
                            "_model": "registry.ReferenceSystem",
                            "_base_xpath": "./wfs:DefaultCRS",
                            "_create_mode": "get_or_create",
                            "_parser": "registry.mappers.parsers.wfs.parse_reference_system",
                            "_reverse": {
                                "_identifier": {
                                    "compiler": "registry.mappers.identifiers.wfs_default_reference_system_identifier",
                                },
                            },
                        },
                        "reference_systems": {
                            "_model": "registry.ReferenceSystem",
                            "_base_xpath": "./wfs:OtherCRS",
                            "_create_mode": "get_or_create",
                            "_parser": "registry.mappers.parsers.wfs.parse_reference_systems",
                            "_reverse": {
                                "_identifier": {
                                    "compiler": "registry.mappers.identifiers.wfs_other_reference_system_identifier",
                                },
                            },
                        },
                        "remote_metadata": {
                            "_model": "registry.FeatureTypeRemoteMetadata",
                            "_base_xpath": "./wfs:MetadataURL",
                            "_create_mode": "bulk",
                            "_reverse": {
                                "_identifier": {
                                    "xpath": "./wfs:MetadataURL[@xlink:href='{link}']",
                                },
                            },
                            "fields": {
                                "link": "./@xlink:href"
                            }
                        },
                    }
                },
            }
        }
    },
    ("DescribeFeatureType", "2.0.0"): {
        "_namespaces": {
            "gml": NAMESPACE_LOOKUP["gml_3_2_2"],
            "xsd": NAMESPACE_LOOKUP["xsd"],
            "wfs": NAMESPACE_LOOKUP["wfs_2_0_0"],
        },
        "feature_type_element": {
            "_model": "registry.FeatureTypeProperty",
            "_base_xpath": "//xsd:complexType/xsd:complexContent/xsd:extension/xsd:sequence/xsd:element",
            "_create_mode": "bulk",
            "fields": {
                "name": "./@name",
                "data_type": "./@type",
                "required": {
                    "_inputs": ("./@nillable",),
                    "_parser": "registry.mappers.parsers.value.str_to_bool",
                    "_reverse_parser": "registry.mappers.parsers.value.boolean_to_int"
                },
                "max_occurs": {
                    "_inputs": ("./@maxOccurs",),
                    "_parser": "registry.mappers.parsers.value.str_to_int",
                },
                "min_occurs": {
                    "_inputs": ("./@min_occurs",),
                    "_parser": "registry.mappers.parsers.value.str_to_int",
                },
            }
        }
    }
}
