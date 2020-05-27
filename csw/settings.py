"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from MrMap.settings import ROOT_URL
from csw.utils.parameter import RESULT_TYPE_CHOICES, ELEMENT_SET_CHOICES

CSW_CACHE_TIME = 60 * 60  # 60 minutes (min * sec)

csw_url = "{}/csw".format(ROOT_URL)
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
        "operations": {
            "GetCapabilities": {
                "get_uri": csw_url,
                "post_uri": csw_url,
                "parameter": {
                    "sections": [
                        "ServiceIdentification",
                        "ServiceProvider",
                        "OperationsMetadata",
                        "Filter_Capabilities"
                    ]
                },
                "constraint": {
                    "PostEncoding": [
                        "XML",
                    ]
                },
            },
            "GetRecords": {
                "get_uri": csw_url,
                "post_uri": csw_url,
                "parameter": {
                    "resultType": RESULT_TYPE_CHOICES.keys(),
                    "ElementSetName": ELEMENT_SET_CHOICES.keys(),
                    "outputFormat": [
                        "application/xml"
                    ],
                    "outputSchema": [
                        "http://www.isotc211.org/2005/gmd",
                        "http://www.opengis.net/cat/csw/2.0.2",
                    ],
                    "typeNames": [
                        "csw:Record",
                        "gmd:MD_Metadata",
                    ],
                    "CONSTRAINTLANGUAGE": [
                        "CQL_TEXT",
                        "FILTER",
                    ],
                },
                "constraint": {
                    "PostEncoding": [
                        "XML",
                    ]
                },
            },
            "GetRecordById": {
                "get_uri": csw_url,
                "post_uri": csw_url,
                "parameter": {
                    "outputFormat": [
                        "application/xml"
                    ],
                    "outputSchema": [
                        "http://www.isotc211.org/2005/gmd",
                        "http://www.opengis.net/cat/csw/2.0.2",
                    ],
                    "typeNames": [
                        "csw:Record",
                        "gmd:MD_Metadata",
                    ],
                    "ElementSetName": ELEMENT_SET_CHOICES.keys(),
                    "resultType": RESULT_TYPE_CHOICES.keys(),
                },
                "constraint": {
                    "PostEncoding": [
                        "XML",
                    ]
                },
            },
        },
        "parameters": {
            "service": [
                "http://www.opengis.net/cat/csw/2.0.2",
            ],
            "version": [
                "2.0.2",
            ],
        },
        "constraints": {
            "iso_profiles": [
                "http://www.isotc211.org/2005/gmd",
            ],
        },
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