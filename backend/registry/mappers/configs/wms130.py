from registry.mappers.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE

XPATH_MAP = {
    ("WMS", "1.3.0"): {
        "_namespaces": {
            "xlink": XLINK_NAMESPACE,
            "wms": WMS_1_3_0_NAMESPACE
        },
        "_schema": "https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd",
        "_pre_save": "registry.mappers.extensions.compute_layer_mptt",
        "service": {
            "_model": "registry.WebMapService",
            "_base_xpath": "/wms:WMS_Capabilities",
            "fields": {
                "version": "./@version",
                "title": "./wms:Service/wms:Title",
                "abstract": "./wms:Service/wms:Abstract",
                "fees": "./wms:Service/wms:Fees",
                "access_constraints": "./wms:Service/wms:AccessConstraints",
                "service_url": "./wms:Service/wms:OnlineResource/@xlink:href",
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
                    "_parser": "registry.mappers.parsers.parse_operation_urls",
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
                        "mptt_parent": "../../wms:Layer",
                        "title": "./wms:Title",
                        "abstract": "./wms:Abstract",
                        "identifier": "./wms:Name",
                        "scale_min": "./wms:MinScaleDenominator",
                        "scale_max": "./wms:MaxScaleDenominator",
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
                            "_inputs": (
                                "./wms:EX_GeographicBoundingBox/wms:westBoundLongitude",
                                "./wms:EX_GeographicBoundingBox/wms:eastBoundLongitude",
                                "./wms:EX_GeographicBoundingBox/wms:southBoundLatitude",
                                "./wms:EX_GeographicBoundingBox/wms:northBoundLatitude"),
                            "_parser": "registry.mappers.parsers.bbox_to_polygon",
                            "_reverse_parser": "registry.mappers.parsers.polygon_to_bbox"
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
                        # TODO: model has no fk to the layer/service objects.
                        # Use _parser or redesign model
                        # "remote_metadata": {
                        #     "_model": "registry.RemoteMetadata",
                        #     "_base_xpath": "./wms:MetadataURL/wms:OnlineResource",
                        #     "fields": {
                        #         "link": "./@xlink:href"
                        #     }
                        # },
                        "time_extents": {
                            "_model": "registry.LayerTimeExtent",
                            "_base_xpath": "./wms:Dimension[@name='time']",
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
