from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

XPATH_MAP = {
    # (Service-Klasse, Version) -> Mapping Feldname -> XPath
    ("WMS", "1.1.1"): {
        "_namespaces": {
            "xlink": NAMESPACE_LOOKUP["xlink"],
            "inspire_common": NAMESPACE_LOOKUP["inspire_common"],
            "inspire_vs": NAMESPACE_LOOKUP["inspire_vs"]
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
                "remote_metadata": {
                    "_model": "registry.WebMapServiceRemoteMetadata",
                    "_base_xpath": "./Capability/VendorSpecificCapabilities/inspire_vs:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./Capability/VendorSpecificCapabilities/inspire_vs:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL/[text()='{link}']",
                        },
                    },
                    "fields": {
                        "link": "./."
                    }
                },
                "service_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./Service/ContactInformation",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./Service/ContactInformation",
                        },
                    },
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
                    "_base_xpath": "./Service/ContactInformation",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./Service/ContactInformation",
                        },
                    },
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
                    "_parser": "registry.mappers.parsers.wms.parse_operation_urls",
                    "_reverse_parser": "registry.mappers.parsers.wms.reverse_parse_operation_urls",
                    "_reverse": {
                        "_identifier": {
                            "compiler": "registry.mappers.identifiers.wms_operation_url_identifier"
                        },
                    },
                },
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "./Service/KeywordList/Keyword",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./Service/KeywordList/Keyword[text()='{keyword}']",
                        },
                    },
                    "fields": {
                        "keyword": "./."
                    }
                },
                "layers": {
                    "_model": "registry.Layer",
                    "_base_xpath": "/WMT_MS_Capabilities/Capability//Layer",
                    "_create_mode": "bulk",
                    "_reverse": {
                        "_identifier": {
                            "compiler": "registry.mappers.identifiers.layer_identifier",
                        },
                        "_ignore_fields": ["mptt_parent"]
                    },
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
                            "_reverse": {
                                "_identifier": {
                                    "xpath": "./KeywordList/Keyword[text()='{keyword}']",
                                },
                            },
                            "fields": {
                                "keyword": "./."
                            }
                        },
                        "reference_systems": {
                            "_model": "registry.ReferenceSystem",
                            "_base_xpath": "./SRS",
                            "_create_mode": "get_or_create",
                            "_reverse": {
                                "_identifier": {
                                    "xpath": "./SRS[text()='{prefix}:{code}']",
                                },
                            },
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
                            "_reverse": {
                                "_identifier": {
                                    "xpath": "./Style/Name[text()='{name}']",
                                },
                            },
                            "fields": {
                                "name": "./Name",
                                "title": "./Title",
                                "legend_url": {
                                    "_model": "registry.LegendUrl",
                                    "_base_xpath": "./LegendURL",
                                    "_create_mode": "bulk",
                                    "_reverse": {
                                        "_identifier": {
                                            "xpath": "./OnlineResource/[@xlink:href='{legend_url}']",
                                        },
                                    },
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
                            "_model": "registry.LayerRemoteMetadata",
                            "_base_xpath": "./MetadataURL/OnlineResource",
                            "_create_mode": "bulk",
                            "_reverse": {
                                "_identifier": {
                                    "xpath": "./MetadataURL/OnlineResource[@xlink:href='{link}']",
                                },
                            },
                            "fields": {
                                "link": "./@xlink:href"
                            }
                        },
                        "time_extents": {
                            "_model": "registry.TimeExtent",
                            "_base_xpath": "./Extent[@name='time']",
                            "_create_mode": "get_or_create",
                            "_reverse": {
                                "_identifier": {
                                    "xpath": "./Extent[@name='time'][text()='{value}']",
                                    "parser": "registry.mappers.parsers.wms.timeextent_to_value"
                                },
                            },
                            "_parser": "registry.mappers.parsers.wms.parse_timeextent",
                        },
                    }
                }
            }
        }
    },
}
