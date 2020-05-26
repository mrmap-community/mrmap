"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""

CSW_CACHE_TIME = 60 * 60  # 60 minutes (min * sec)

CSW_CAPABILITIES_CONF = {
    "service_identification": {
        "title": "Mr.Map CSW",
        "abstract": "The catalogue service for the web interface of Mr.Map",
        "keywords": "1,2,3,4",
        "service_type": "CSW",
        "service_type_version": "2.0.2",
        "fees": "",
        "access_constraints": "",
    },
    "service_provider": {
        "name": "GDI-RP",
        "provider_site": "testsite",
        "individual_name": "admin admin",
        "position_name": "Administrator",
        "contact_phone": "0123456789",
        "contact_facsimile": "9874563210",
        "contact_address_delivery_point": "",
        "contact_address_city": "Coblenz",
        "contact_address_administrative_area": "Rhineland-Palatinate",
        "contact_address_postal_code": "56070",
        "contact_address_country": "Germany",
        "contact_address_email": "test@test.com",
        "contact_hours_of_service": "24/7",
        "contact_contact_instructions": "None",
        "contact_contact_info": "None",
        "contact_role": "pointOfContact",
    },
    "operations_metadata": {
        "GetCapabilities": {
            "get_uri": "",
            "post_uri": "",
            "sections": [
                "ServiceIdentification",
                "ServiceProvider",
                "OperationsMetadata",
                "Filter_Capabilities"
            ],
            "post_encoding": [
                "XML",
            ]
        },
        "GetRecords": {
            "get_uri": "",
            "post_uri": "",
            "result_type": [
                "hits",
                "results",
                "validate",
            ],
            "output_format": [
                "application/xml"
            ],
            "output_schema": [
                "http://www.isotc211.org/2005/gmd",
                "http://www.opengis.net/cat/csw/2.0.2",
            ],
            "type_names": [
                "csw:Record",
                "gmd:MD_Metadata",
            ],
            "constraint_language": [
                "CQL_TEXT",
                "FILTER",
            ],
            "post_encoding": [
                "XML",
            ]
        },
        "GetRecordById": {
            "get_uri": "",
            "post_uri": "",
            "output_format": [
                "application/xml"
            ],
            "output_schema": [
                "http://www.isotc211.org/2005/gmd",
                "http://www.opengis.net/cat/csw/2.0.2",
            ],
            "type_names": [
                "csw:Record",
                "gmd:MD_Metadata",
            ],
            "ElementSetName": [
                "brief",
                "summary",
                "full",
            ],
            "result_type": [
                "hits",
                "results",
                "validate",
            ],
            "post_encoding": [
                "XML",
            ]
        },
        "service": "http://www.opengis.net/cat/csw/2.0.2",
        "version": "2.0.2",
        "iso_profiles": "http://www.isotc211.org/2005/gmd",
    },
    "filter_capabilities": {
        "scalar_capabilities": {
            "comparison_operators": [
                "PropertyIsEqualTo",
                "PropertyIsLike",
                "PropertyIsLessThan",
                "PropertyIsGreaterThan",
                "PropertyIsLessThanOrEqualTo",
                "PropertyIsGreaterThanOrEqualTo",
                "PropertyIsNotEqualTo",
            ]
        }
    }
}