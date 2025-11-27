from registry.mappers.namespaces import (FES_2_0_NAMEPSACE,
                                         GML_3_2_2_NAMESPACE, INSPIRE_COMMON,
                                         INSPIRE_VS, OWS_1_1_NAMESPACE,
                                         WFS_2_0_0_NAMESPACE, XLINK_NAMESPACE)

XPATH_MAP = {
    # (Service-Klasse, Version) -> Mapping Feldname -> XPath
    ("WFS", "2.0.0"): {
        "_namespaces": {
            "xlink": XLINK_NAMESPACE,
            "wfs": WFS_2_0_0_NAMESPACE,
            "ows": OWS_1_1_NAMESPACE,
            "gml": GML_3_2_2_NAMESPACE,
            "fes": FES_2_0_NAMEPSACE,
            "inspire_common": INSPIRE_COMMON,
            "inspire_vs": INSPIRE_VS
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
                    "_base_xpath": "/wfs:WFS_Capabilities/ows:OperationsMetadata/ows:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL",
                    "fields": {
                        "link": "./."
                    }
                },
                "service_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "/wfs:WFS_Capabilities/ows:ServiceProvider",
                    "_create_mode": "get_or_create",
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
                    "_base_xpath": "/wfs:WFS_Capabilities/ows:ServiceProvider",
                    "_create_mode": "get_or_create",
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
                    "_base_xpath": "/wfs:WFS_Capabilities/ows:OperationsMetadata/ows:Operation/ows:DCP/ows:HTTP//*[self::ows:Post or self::ows:Get]",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "method": {
                            "_inputs": (".",),
                            "_parser": "registry.mappers.parsers.value.method_to_enum",
                            "_reverse_parser": "registry.mappers.parsers.value.enum_to_method",
                        },
                        "operation": {
                            "_inputs": ("../../../@name",),
                            "_parser": "registry.mappers.parsers.value.operation_to_enum",
                            "_reverse_parser": "registry.mappers.parsers.value.enum_to_operation"
                        },
                        "url": "./@xlink:href",
                        "mime_types": {
                            "_model": "registry.MimeType",
                            "_base_xpath": '../../../ows:Parameter[@name="outputFormat"]/ows:Value',
                            "_create_mode": "get_or_create",
                            "_many": True,
                            "fields": {
                                "mime_type": "."
                            }
                        }
                    },
                },
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "/wfs:WFS_Capabilities/ows:ServiceIdentification/ows:Keywords/ows:Keyword",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "keyword": "./."
                    }
                },
                "featuretypes": {
                    "_model": "registry.FeatureType",
                    "_base_xpath": "/wfs:WFS_Capabilities/wfs:FeatureTypeList/wfs:FeatureType",
                    "_create_mode": "bulk",
                    "_many": True,
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
                            "_many": True,
                            "fields": {
                                "keyword": "./."
                            }
                        },
                        "output_formats": {
                            "_model": "registry.MimeType",
                            "_base_xpath": "./wfs:OutputFormats/wfs:Format",
                            "_create_mode": "get_or_create",
                            "_many": True,
                            "fields": {
                                "mime_type": "./."
                            }
                        },
                        "reference_systems": {
                            "_model": "registry.ReferenceSystem",
                            "_base_xpath": "./.",
                            "_create_mode": "get_or_create",
                            "_many": True,
                            "_parser": "registry.mappers.parsers.wfs.parse_reference_systems",
                        },
                        "remote_metadata": {
                            "_model": "registry.FeatureTypeRemoteMetadata",
                            "_base_xpath": "./wfs:MetadataURL",
                            "_create_mode": "bulk",
                            "fields": {
                                "link": "./@xlink:href"
                            }
                        },
                    }
                },
            }
        }
    },
}
