from registry.fields.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE

XPATH_MAP = {
    # (Service-Klasse, Version) -> Mapping Feldname -> XPath
    ("WMS", "1.1.1"): {
        "_namespaces": {
            "xlink": XLINK_NAMESPACE,
            "wms": WMS_1_3_0_NAMESPACE
        },
        "_schema": "http://schemas.opengis.net/wms/1.1.1/WMS_MS_Capabilities.dtd",
        "_root": "/wms:WMT_MS_Capabilities",
        "service": {
            "_model": "registry.WebMapService",
            "version": "/@version",
            "title": "/wms:Service/wms:Title",
            "abstract": "/wms:Service/wms:Abstract",
            "fees": "/wms:Service/wms:Fees",
            "access_constraints": "/wms:Service/wms:AccessConstraints",
            "service_url": "./Service/OnlineResource/@xlink:href"
        },
        "layers": {
            "_xpath": "./wms:Capability/wms:Layer/wms:Layer",  # Liste
            "_model": "registry.Layer",
            "name": "./wms:Name",
            "title": "./wms:Title",
            "bbox_lat_lon": {
                "_inputs": ("/LatLonBoundingBox/@minx", "./LatLonBoundingBox/@maxx", "./LatLonBoundingBox/@miny", "./LatLonBoundingBox/@maxy"),
                "_parser": "parsers.bbox_to_polygon",
                "_reverse_parser": "parsers.polygon_to_bbox"
            },
            "styles": {
                "_xpath": "./wms:Style",  # Nested Liste
                "_model": "StyleModel",
                "name": "./wms:Name",
                "title": "./wms:Title"
            }
        },
        "service_contact": {
            "_root": "/wms:ContactInformation",
            "_model": "registry.MetadataContact",
            "name": "ContactPersonPrimary/ContactOrganization",
            "person_name": "ContactPersonPrimary/ContactPerson",
            "phone": "ContactVoiceTelephone",
            "facsimile": "ContactFacsimileTelephone",
            "email": "ContactElectronicMailAddress",
            "country": "ContactAddress/Country",
            "postal_code": "ContactAddress/PostCode",
            "city": "ContactAddress/City",
            "state_or_province": "ContactAddress/StateOrProvince",
            "address": "ContactAddress/Address"
        },
        "keywords": {
            "_xpath": "./Service/KeywordList/Keyword",  # Liste
            "keyword": "."
        },

    },
    ("WMS", "1.3.0"): {
        "title": "/wms:WMS_Capabilities/wms:Service/wms:Title",
        "abstract": "/wms:WMS_Capabilities/wms:Service/wms:Abstract"
    },
    ("WFS", "2.0.0"): {
        "title": "/wfs:WFS_Capabilities/wfs:Service/wfs:Title"
    },
    ("CSW", "2.0.2"): {
        "title": "/csw:Capabilities/csw:Service/csw:Title"
    }
}
