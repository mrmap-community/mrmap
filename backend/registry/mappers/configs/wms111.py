from registry.mappers.namespaces import XLINK_NAMESPACE

XPATH_MAP = {
    # (Service-Klasse, Version) -> Mapping Feldname -> XPath
    ("WMS", "1.1.1"): {
        "_namespaces": {
            "xlink": XLINK_NAMESPACE
        },
        "_schema": "http://schemas.opengis.net/wms/1.1.1/WMS_MS_Capabilities.dtd",
        "_pre_save": "registry.mappers.extensions.compute_layer_mptt",
        "service": {
            "_model": "registry.WebMapService",
            "_base_xpath": "/WMT_MS_Capabilities",
            "fields": {
                "version": "./@version",
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
                    "_parser": "registry.mappers.parsers.parse_operation_urls",
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
                        "mptt_parent": "../../Layer",
                        "title": "./Title",
                        "abstract": "./Abstract",
                        "identifier": "./Name",
                        "scale_min": "./ScaleHint/@min",
                        "scale_max": "./ScaleHint/@max",
                        "is_queryable": {
                            "_inputs": ("./@queryable",),
                            "_default": "0",
                            "_parser": "registry.mappers.parsers.str_to_bool",
                            "_reverse_parser": "registry.mappers.parsers.boolean_to_int"
                        },
                        "is_opaque": {
                            "_inputs": ("./@opaque",),
                            "_default": "0",
                            "_parser": "registry.mappers.parsers.str_to_bool",
                            "_reverse_parser": "registry.mappers.parsers.boolean_to_int"
                        },
                        "is_cascaded": {
                            "_inputs": ("./@cascaded",),
                            "_default": "0",
                            "_parser": "registry.mappers.parsers.str_to_bool",
                            "_reverse_parser": "registry.mappers.parsers.boolean_to_int"
                        },
                        "bbox_lat_lon": {
                            "_inputs": ("./LatLonBoundingBox/@minx", "./LatLonBoundingBox/@maxx", "./LatLonBoundingBox/@miny", "./LatLonBoundingBox/@maxy"),
                            "_parser": "registry.mappers.parsers.bbox_to_polygon",
                            "_reverse_parser": "registry.mappers.parsers.polygon_to_bbox"
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
                                    "_inputs": ("./.",),
                                    "_parser": "registry.mappers.parsers.srs_to_code",
                                },
                                "prefix": {
                                    "_inputs": ("./.",),
                                    "_parser": "registry.mappers.parsers.srs_to_prefix",
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
                        # TODO: model has no fk to the layer/service objects.
                        # Use _parser or redesign model
                        # "remote_metadata": {
                        #     "_model": "registry.RemoteMetadata",
                        #     "_base_xpath": "./MetadataURL/OnlineResource",
                        #     "fields": {
                        #         "link": "./@xlink:href"
                        #     }
                        # },
                        "time_extents": {
                            "_model": "registry.LayerTimeExtent",
                            "_base_xpath": "./Extent[@name='time']",
                            "_create_mode": "bulk",
                            "_many": True,
                            "_parser": "registry.mappers.parsers.parse_timeextent",
                        },
                    }
                }
            }
        }
    },
}
