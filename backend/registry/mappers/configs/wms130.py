from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

XPATH_MAP = {
    ("WMS", "1.3.0"): {
        "_namespaces": {
            "xlink": NAMESPACE_LOOKUP["xlink"],
            "wms": NAMESPACE_LOOKUP["wms_1_3_0"],
            "inspire_common": NAMESPACE_LOOKUP["inspire_common"],
            "inspire_vs": NAMESPACE_LOOKUP["inspire_vs"]
        },
        "_schema": "https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd",
        "_pre_save": [
            "registry.mappers.extensions.compute_layer_mptt",
            "registry.mappers.extensions.clean_up_operation_urls"
        ],
        "service": {
            "_model": "registry.WebMapService",
            "_base_xpath": "/wms:WMS_Capabilities",
            "fields": {
                "version": {
                    "_inputs": ("./@version",),
                    "_parser": "registry.mappers.parsers.value.version_to_int",
                    "_reverse_parser": "registry.mappers.parsers.value.int_to_version"
                },
                "title": "./wms:Service/wms:Title",
                "abstract": "./wms:Service/wms:Abstract",
                "fees": "./wms:Service/wms:Fees",
                "access_constraints": "./wms:Service/wms:AccessConstraints",
                "service_url": "./wms:Service/wms:OnlineResource/@xlink:href",
                "remote_metadata": {
                    "_model": "registry.WebMapServiceRemoteMetadata",
                    "_base_xpath": "/wms:WMS_Capabilities/wms:Capability/inspire_vs:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL",
                    "fields": {
                        "link": "./."
                    }
                },
                "service_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "/wms:WMS_Capabilities/wms:Service/wms:ContactInformation",
                    "_create_mode": "get_or_create",
                    "fields": {
                        "name": "./wms:ContactPersonPrimary/wms:ContactOrganization",
                        "person_name": "./wms:ContactPersonPrimary/wms:ContactPerson",
                        "phone": "./wms:ContactVoiceTelephone",
                        "facsimile": "./wms:ContactFacsimileTelephone",
                        "email": "./wms:ContactElectronicMailAddress",
                        "country": "./wms:ContactAddress/wms:Country",
                        "postal_code": "./wms:ContactAddress/wms:PostCode",
                        "city": "./wms:ContactAddress/wms:City",
                        "state_or_province": "./wms:ContactAddress/wms:StateOrProvince",
                        "address": "./wms:ContactAddress/wms:Address"
                    }
                },
                "metadata_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "/wms:WMS_Capabilities/wms:Service/wms:ContactInformation",
                    "_create_mode": "get_or_create",
                    "fields": {
                        "name": "./wms:ContactPersonPrimary/wms:ContactOrganization",
                        "person_name": "./wms:ContactPersonPrimary/wms:ContactPerson",
                        "phone": "./wms:ContactVoiceTelephone",
                        "facsimile": "./wms:ContactFacsimileTelephone",
                        "email": "./wms:ContactElectronicMailAddress",
                        "country": "./wms:ContactAddress/wms:Country",
                        "postal_code": "./wms:ContactAddress/wms:PostCode",
                        "city": "./wms:ContactAddress/wms:City",
                        "state_or_province": "./wms:ContactAddress/wms:StateOrProvince",
                        "address": "./wms:ContactAddress/wms:Address"
                    }
                },
                "operation_urls": {
                    "_model": "registry.WebMapServiceOperationUrl",
                    "_base_xpath": "./wms:Capability/wms:Request",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "_parser": "registry.mappers.parsers.wms.parse_operation_urls",
                    "_reverse_parser": "registry.mappers.parsers.wms.reverse_parse_operation_urls",
                },
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "/wms:WMS_Capabilities/wms:Service/wms:KeywordList/wms:Keyword",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "keyword": "./."
                    }
                },
                "layers": {
                    "_model": "registry.Layer",
                    "_base_xpath": "/wms:WMS_Capabilities/wms:Capability//wms:Layer",
                    "_create_mode": "bulk",
                    "_many": True,
                    "fields": {
                        "mptt_parent": "..",
                        "title": "./wms:Title",
                        "abstract": "./wms:Abstract",
                        "identifier": "./wms:Name",
                        "scale_min": "./wms:MinScaleDenominator",
                        "scale_max": "./wms:MaxScaleDenominator",
                        "is_queryable": {
                            "_inputs": ("./@queryable",),
                            "_default": "0",
                            "_parser": "registry.mappers.parsers.value.str_to_bool",
                            "_reverse_parser": "registry.mappers.parsers.value.boolean_to_int"
                        },
                        "is_opaque": {
                            "_inputs": ("./@opaque",),
                            "_default": "0",
                            "_parser": "registry.mappers.parsers.value.str_to_bool",
                            "_reverse_parser": "registry.mappers.parsers.value.boolean_to_int"
                        },
                        "is_cascaded": {
                            "_inputs": ("./@cascaded",),
                            "_default": "0",
                            "_parser": "registry.mappers.parsers.value.str_to_bool",
                            "_reverse_parser": "registry.mappers.parsers.value.boolean_to_int"
                        },
                        "bbox_lat_lon": {
                            "_inputs": (
                                "./wms:EX_GeographicBoundingBox/wms:westBoundLongitude/text()",
                                "./wms:EX_GeographicBoundingBox/wms:eastBoundLongitude/text()",
                                "./wms:EX_GeographicBoundingBox/wms:southBoundLatitude/text()",
                                "./wms:EX_GeographicBoundingBox/wms:northBoundLatitude/text()"),
                            "_parser": "registry.mappers.parsers.value.bbox_to_polygon",
                            "_reverse_parser": "registry.mappers.parsers.value.polygon_to_bbox"
                        },
                        "keywords": {
                            "_model": "registry.Keyword",
                            "_base_xpath": "./wms:KeywordList/wms:Keyword",
                            "_create_mode": "get_or_create",
                            "_many": True,
                            "fields": {
                                "keyword": "./."
                            }
                        },
                        "reference_systems": {
                            "_model": "registry.ReferenceSystem",
                            "_base_xpath": "./wms:CRS",
                            "_create_mode": "get_or_create",
                            "_many": True,
                            "fields": {
                                "code": {
                                    "_inputs": ("./text()",),
                                    "_parser": "registry.mappers.parsers.value.srs_to_code",
                                },
                                "prefix": {
                                    "_inputs": ("./text()",),
                                    "_parser": "registry.mappers.parsers.value.srs_to_prefix",
                                }
                            }
                        },
                        "styles": {
                            "_model": "registry.Style",
                            "_base_xpath": "./wms:Style",
                            "_create_mode": "bulk",
                            "_many": True,
                            "fields": {
                                "name": "./wms:Name",
                                "title": "./wms:Title",
                                "legend_url": {
                                    "_model": "registry.LegendUrl",
                                    "_base_xpath": "./wms:LegendURL",
                                    "_create_mode": "bulk",
                                    "fields": {
                                        "height": "./@height",
                                        "width": "./@width",
                                        "legend_url": "./OnlineResource/@xlink:href",
                                        "mime_type": {
                                            "_model": "registry.MimeType",
                                            "_base_xpath": "./wms:Format",
                                            "_create_mode": "get_or_create",
                                            "fields": {
                                                "mime_type": "./."
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        "remote_metadata": {
                            "_model": "registry.LayerRemoteMetadata",
                            "_base_xpath": "./wms:MetadataURL/wms:OnlineResource",
                            "_create_mode": "bulk",
                            "fields": {
                                "link": "./@xlink:href"
                            }
                        },
                        "time_extents": {
                            "_model": "registry.TimeExtent",
                            "_base_xpath": "./wms:Dimension[@name='time']",
                            "_create_mode": "get_or_create",
                            "_many": True,
                            "_parser": "registry.mappers.parsers.wms.parse_timeextent",
                        },
                    }
                }
            }
        }
    },
}
