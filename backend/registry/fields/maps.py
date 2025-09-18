from registry.fields.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE

XPATH_MAP = {
    # (Service-Klasse, Version) -> Mapping Feldname -> XPath
    ("WMS", "1.1.1"): {
        "_namespaces": {
            "xlink": XLINK_NAMESPACE,
            "wms": WMS_1_3_0_NAMESPACE
        },
        "_schema": "http://schemas.opengis.net/wms/1.1.1/WMS_MS_Capabilities.dtd",
        "title": "/wms:WMT_MS_Capabilities/wms:Service/wms:Title",
        "abstract": "/wms:WMT_MS_Capabilities/wms:Service/wms:Abstract",
        "fees": "/wms:WMT_MS_Capabilities/wms:Service/wms:Fees",
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
