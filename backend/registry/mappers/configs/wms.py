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
                "version": "/@version",
                "title": "/Service/Title",
                "abstract": "/Service/Abstract",
                "fees": "/Service/Fees",
                "access_constraints": "/Service/AccessConstraints",
                "service_url": "/Service/OnlineResource/@xlink:href",
                "service_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "/WMT_MS_Capabilities/ContactInformation",
                    "_create_mode": "get_or_create",
                    "fields": {
                        "name": "/ContactPersonPrimary/ContactOrganization",
                        "person_name": "/ContactPersonPrimary/ContactPerson",
                        "phone": "/ContactVoiceTelephone",
                        "facsimile": "/ContactFacsimileTelephone",
                        "email": "/ContactElectronicMailAddress",
                        "country": "/ContactAddress/Country",
                        "postal_code": "/ContactAddress/PostCode",
                        "city": "/ContactAddress/City",
                        "state_or_province": "/ContactAddress/StateOrProvince",
                        "address": "/ContactAddress/Address"
                    }
                },
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "/WMT_MS_Capabilities/Service/KeywordList/Keyword",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "keyword": "/."
                    }
                },
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
                # "layers": {
                #     "_model": "registry.Layer",
                #     "_xpath": "./Capability/Layer/",
                #     "fields": {
                #         "name": "./wms:Name",
                #         "title": "./wms:Title",
                #         "identifier": "./Name",
                #         "is_queryable": {
                #             "_inputs": ("./@queryable",),
                #             "_parser": "parsers.int_to_boolean",
                #             "_reverse_parser": "parsers.boolean_to_int"
                #         },
                #         "is_opaque": {
                #             "_inputs": ("./@opaque",),
                #             "_parser": "parsers.int_to_boolean",
                #             "_reverse_parser": "parsers.boolean_to_int"
                #         },
                #         "is_cascaded": {
                #             "_inputs": ("./@cascaded",),
                #             "_parser": "parsers.int_to_boolean",
                #             "_reverse_parser": "parsers.boolean_to_int"
                #         },
                #         "scale_min": "./ScaleHint/@min",
                #         "scale_max": "./ScaleHint/@max",
                #         "bbox_lat_lon": {
                #             "_inputs": ("/LatLonBoundingBox/@minx", "./LatLonBoundingBox/@maxx", "./LatLonBoundingBox/@miny", "./LatLonBoundingBox/@maxy"),
                #             "_parser": "parsers.bbox_to_polygon",
                #             "_reverse_parser": "parsers.polygon_to_bbox"
                #         },

                #     },
                #     "relations": {
                #         "parent": {
                #             "_model": "registry.Layer",
                #             "_xpath": "../..Layer",
                #         },
                #         "service": {
                #             "_model": "registry.WebMapService",  # relate the service of this config
                #         },
                #         "reference_system": {
                #             "_model": "registry.ReferenceSystem",
                #             "_xpath": "./SRS",
                #         },
                #         "keywords": {
                #             "_model": "registry.Keyword",
                #             "_xpath": "./KeywordList/Keyword",
                #         }
                #     },
                #     "reverse_relation": {
                #         "styles": {
                #             "_model": "registry.Style",
                #             "_xpath": "./wms:Style",
                #             "name": "./wms:Name",
                #             "title": "./wms:Title"
                #         },
                #     }
                # },
            }
        },


    }
}
