from registry.mappers.namespaces import XLINK_NAMESPACE

XPATH_MAP = {
    # (Service-Klasse, Version) -> Mapping Feldname -> XPath
    ("WMS", "1.1.1"): {
        "_namespaces": {
            "xlink": XLINK_NAMESPACE
        },
        "_schema": "http://schemas.opengis.net/wms/1.1.1/WMS_MS_Capabilities.dtd",
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
                            "_many": True,
                            "fields": {
                                "name": "./Name",
                                "title": "./Title",
                                "legend_url": {
                                    "_model": "registry.LegendUrl",
                                    "_base_xpath": "./LegendURL",
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
                    }
                }
            },

            "reverse_relations": {
                # "operation_urls": {
                #     "_model": "registry.WebMapServiceOperationUrl",
                #     "_aggregate": {
                #               "GetCapabilities": {
                #                   "operation": "GetCapabilities",
                #                   "method": {
                #                       "GET": "./Capability/Request/GetCapabilities/DCPType/HTTP/Get/OnlineResource/@xlink:href",
                #                       "POST": "./Capability/Request/GetCapabilities/DCPType/HTTP/Post/OnlineResource/@xlink:href",
                #                   },
                #                   "mime_types": {
                #                       "_model": "registry.MimeType",
                #                       "mime_type": "./Capability/Request/GetCapabilities/Format",
                #                   },
                #               },
                #         "GetMap": {
                #                   "operation": "GetMap",
                #                   "method": {
                #                       "GET": "./Capability/Request/GetMap/DCPType/HTTP/Get/OnlineResource/@xlink:href",
                #                       "POST": "./Capability/Request/GetMap/DCPType/HTTP/Post/OnlineResource/@xlink:href",
                #                   },
                #                   "mime_types": {
                #                       "_model": "registry.MimeType",
                #                       "mime_type": "./Capability/Request/GetMap/Format",
                #                   },
                #               },
                #         "GetFeatureInfo": {
                #                   "operation": "GetFeatureInfo",
                #                   "method": {
                #                       "GET": "./Capability/Request/GetFeatureInfo/DCPType/HTTP/Get/OnlineResource/@xlink:href",
                #                       "POST": "./Capability/Request/GetFeatureInfo/DCPType/HTTP/Post/OnlineResource/@xlink:href",
                #                   },
                #                   "mime_types": {
                #                       "_model": "registry.MimeType",
                #                       "_xpath": "./Capability/Request/GetFeatureInfo/Format",
                #                       "mime_type": ".",
                #                   },
                #               }
                #     }
                # },


            }
        },


    }
}
