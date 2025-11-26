from registry.mappers.namespaces import (INSPIRE_COMMON, INSPIRE_VS,
                                         XLINK_NAMESPACE)

XPATH_MAP = {
    # (Service-Klasse, Version) -> Mapping Feldname -> XPath
    ("WMS", "1.1.1"): {
        "_namespaces": {
            "xlink": XLINK_NAMESPACE,
            "inspire_common": INSPIRE_COMMON,
            "inspire_vs": INSPIRE_VS
        },
        "_schema": "http://schemas.opengis.net/wms/1.1.1/WMS_MS_Capabilities.dtd",
        "_pre_save": [
            "registry.mappers.extensions.compute_layer_mptt",
            "registry.mappers.extensions.clean_up_operation_urls"
        ],
        "service": {
            "_model": "registry.WebMapService",
            "_base_xpath": "/WMT_MS_Capabilities",
            "fields": {
                "version":  {
                    "_inputs": ("./@version",),
                    "_parser": "registry.mappers.parsers.value.version_to_int",
                    "_reverse_parser": "registry.mappers.parsers.value.int_to_version"
                },
                "title": "./Service/Title",
                "abstract": "./Service/Abstract",
                "fees": "./Service/Fees",
                "access_constraints": "./Service/AccessConstraints",
                "service_url": "./Service/OnlineResource/@xlink:href",
                "service_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "/WMT_MS_Capabilities/Service/ContactInformation",
                    "_create_mode": "get_or_create",
                    "fields": {
                        "name": "./ContactPersonPrimary/ContactOrganization",
                        "person_name": "./ContactPersonPrimary/ContactPerson",
                        "phone": "./ContactVoiceTelephone",
                        "facsimile": "./ContactFacsimileTelephone",
                        "email": "./ContactElectronicMailAddress",
                        "country": "./ContactAddress/Country",
                        "postal_code": "./ContactAddress/PostCode",
                        "city": "./ContactAddress/City",
                        "state_or_province": "./ContactAddress/StateOrProvince",
                        "address": "./ContactAddress/Address"
                    }
                },
                "metadata_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "/WMT_MS_Capabilities/Service/ContactInformation",
                    "_create_mode": "get_or_create",
                    "fields": {
                        "name": "./ContactPersonPrimary/ContactOrganization",
                        "person_name": "./ContactPersonPrimary/ContactPerson",
                        "phone": "./ContactVoiceTelephone",
                        "facsimile": "./ContactFacsimileTelephone",
                        "email": "./ContactElectronicMailAddress",
                        "country": "./ContactAddress/Country",
                        "postal_code": "./ContactAddress/PostCode",
                        "city": "./ContactAddress/City",
                        "state_or_province": "./ContactAddress/StateOrProvince",
                        "address": "./ContactAddress/Address"
                    }
                },
                "operation_urls": {
                    "_model": "registry.WebMapServiceOperationUrl",
                    "_base_xpath": "./Capability/Request",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "_parser": "registry.mappers.parsers.wms.parse_operation_urls",
                },
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "/WMT_MS_Capabilities/Service/KeywordList/Keyword",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "keyword": "./."
                    }
                },
                "layers": {
                    "_model": "registry.Layer",
                    "_base_xpath": "/WMT_MS_Capabilities/Capability//Layer",
                    "_create_mode": "bulk",
                    "_many": True,
                    "fields": {
                        "mptt_parent": "..",
                        "title": "./Title",
                        "abstract": "./Abstract",
                        "identifier": "./Name",
                        "scale_min": "./ScaleHint/@min",
                        "scale_max": "./ScaleHint/@max",
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
                            "_inputs": ("./LatLonBoundingBox/@minx", "./LatLonBoundingBox/@maxx", "./LatLonBoundingBox/@miny", "./LatLonBoundingBox/@maxy"),
                            "_parser": "registry.mappers.parsers.value.bbox_to_polygon",
                            "_reverse_parser": "registry.mappers.parsers.value.polygon_to_bbox"
                        },
                        "keywords": {
                            "_model": "registry.Keyword",
                            "_base_xpath": "./KeywordList/Keyword",
                            "_create_mode": "get_or_create",
                            "_many": True,
                            "fields": {
                                "keyword": "./."
                            }
                        },
                        "reference_systems": {
                            "_model": "registry.ReferenceSystem",
                            "_base_xpath": "./SRS",
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
                            "_base_xpath": "./Style",
                            "_create_mode": "bulk",
                            "_many": True,
                            "fields": {
                                "name": "./Name",
                                "title": "./Title",
                                "legend_url": {
                                    "_model": "registry.LegendUrl",
                                    "_base_xpath": "./LegendURL",
                                    "_create_mode": "bulk",
                                    "fields": {
                                        "height": "./@height",
                                        "width": "./@width",
                                        "legend_url": "./OnlineResource/@xlink:href",
                                        "mime_type": {
                                            "_model": "registry.MimeType",
                                            "_base_xpath": "./Format",
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
                            "_model": "registry.WebMapServiceRemoteMetadata",
                            "_base_xpath": "./VendorSpecificCapabilities/inspire_vs:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL",
                            "fields": {
                                "link": "./text()"
                            }
                        },
                        "time_extents": {
                            "_model": "registry.LayerTimeExtent",
                            "_base_xpath": "./Extent[@name='time']",
                            "_create_mode": "bulk",
                            "_many": True,
                            "_parser": "registry.mappers.parsers.wms.parse_timeextent",
                        },
                    }
                }
            }
        }
    },
}
