XSD_LOOKUP = {
    ("wfs", "GetCapabilitites", "2.0.0"): "wfsCapabilitites200.xsd",
    ("wfs", "GetCapabilitites", "2.0.2"): "wfsCapabilitites200.xsd",
    ("wfs", "Exception", "2.0.0"): "wfsExceptionReport202.xsd",
    ("wms", "Exception", "1.1.1"): "wmsExceptionReport111.xsd",
    ("wms", "Exception", "1.3.0"): "wmsExceptionReport130.xsd",
    ("csw", "discovery", "2.0.2"): "cswDiscovery.xsd",
    ("csw", "Exception", "2.0.2"): "owsExceptionReport.xsd",
    ("ows", "common", "1.0.0"): "owsAll.xsd",
}

# The plain http URIs of this lookup are the normative XML namespace identifiers of the ISO and
# INSPIRE schemas. They are registered with and compared literally by lxml and are never resolved
# or requested over the network, so the insecure transport findings on them are false positives
# and are suppressed in place below.
NAMESPACE_LOOKUP = {
    "ns_wc": "*[local-name()='",
    "gmd": "http://www.isotc211.org/2005/gmd",  # NOSONAR normative ISO 19139 gmd namespace identifier, compared literally by lxml - not a network endpoint
    "gco": "http://www.isotc211.org/2005/gco",  # NOSONAR normative ISO 19103 gco namespace identifier, compared literally by lxml - not a network endpoint
    "gmx": "http://www.isotc211.org/2005/gmx",  # NOSONAR normative ISO 19115-2 gmx namespace identifier, compared literally by lxml - not a network endpoint
    "srv": "http://www.isotc211.org/2005/srv",  # NOSONAR normative ISO 19139 srv namespace identifier, compared literally by lxml - not a network endpoint
    "gml_3_1_1": "http://www.opengis.net/gml",
    "gml_3_2_2": "http://www.opengis.net/gml/3.2",
    "xlink": "http://www.w3.org/1999/xlink",
    "csw_2_0_2": "http://www.opengis.net/cat/csw/2.0.2",
    "wfs_1_1_2": "http://www.opengis.net/wfs",
    "wfs_2_0_0": "http://www.opengis.net/wfs/2.0",
    "wms_1_3_0": "http://www.opengis.net/wms",
    "ows": "http://www.opengis.net/ows",
    "ows_1_1": "http://www.opengis.net/ows/1.1",
    "fes_2_0": "http://www.opengis.net/fes/2.0",
    "ogc": "http://www.opengis.net/ogc",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "xsd": "http://www.w3.org/2001/XMLSchema",
    "inspire_common": "http://inspire.ec.europa.eu/schemas/common/1.0",  # NOSONAR normative INSPIRE common schema namespace identifier, compared literally by lxml - not a network endpoint
    "inspire_vs": "http://inspire.ec.europa.eu/schemas/inspire_vs/1.0"  # NOSONAR normative INSPIRE view services schema namespace identifier, compared literally by lxml - not a network endpoint
}
