"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 05.05.20

"""
from MrMap.settings import ROOT_URL
from csw.utils.parameter import RESULT_TYPE_CHOICES, ELEMENT_SET_CHOICES

import logging

from service.helper.enums import MetadataEnum

csw_logger = logging.getLogger("MrMap.csw")

CSW_ERROR_LOG_TEMPLATE = "Error on metadata with file identifier '{}' from catalogue '{}'. \nException: {}"
CSW_EXTENT_WARNING_LOG_TEMPLATE = "Error on extent for metadata with file identifier '{}' from catalogue '{}'. \nFound extent data was '{}'. Could not parse correctly. Fallback to default extent."
CSW_GENERIC_ERROR_TEMPLATE = "Error occured on catalogue '{}': \n{}"

# Harvesting
# Set the value to True or False to activate/deactivate the harvesting of these types of metadata.
# "Types of metadata" is equivalent to MD_ScopeCode according to ISO19115
HARVEST_METADATA_TYPES = {
    MetadataEnum.DATASET.value: True,
    MetadataEnum.SERVICE.value: True,
    MetadataEnum.LAYER.value: True,
    MetadataEnum.TILE.value: False,
    MetadataEnum.SERIES.value: True,
    MetadataEnum.FEATURETYPE.value: True,
    MetadataEnum.CATALOGUE.value: True,
    MetadataEnum.ATTRIBUTE.value: True,
    MetadataEnum.ATTRIBUTETYPE.value: True,
    MetadataEnum.COLLECTION_HARDWARE.value: True,
    MetadataEnum.COLLECTION_SESSION.value: True,
    MetadataEnum.NON_GEOGRAPHIC_DATASET.value: True,
    MetadataEnum.DIMENSION_GROUP.value: True,
    MetadataEnum.FEATURE.value: True,
    MetadataEnum.PROPERTYTYPE.value: True,
    MetadataEnum.FIELDSESSION.value: True,
    MetadataEnum.SOFTWARE.value: True,
    MetadataEnum.MODEL.value: True,
}


CSW_CACHE_TIME = 60 * 60  # 60 minutes (min * sec)
CSW_CACHE_PREFIX = "csw"

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
                "parameter": {
                    "sections": [
                        "ServiceIdentification",
                        "ServiceProvider",
                        "OperationsMetadata",
                        "Filter_Capabilities"
                    ]
                },
                "constraint": {
                },
            },
            "GetRecords": {
                "get_uri": csw_url,
                "parameter": {
                    "resultType": list(RESULT_TYPE_CHOICES.keys()),
                    "ElementSetName": list(ELEMENT_SET_CHOICES.keys()),
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
                },
            },
            "GetRecordById": {
                "get_uri": csw_url,
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
                    "ElementSetName": list(ELEMENT_SET_CHOICES.keys()),
                    "resultType": list(RESULT_TYPE_CHOICES.keys()),
                },
                "constraint": {
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
        "Scalar_Capabilities": {
            "ComparisonOperators": [
                "EqualTo",
                "Like",
                "LessThan",
                "GreaterThan",
                "LessThanOrEqualTo",
                "GreaterThanOrEqualTo",
                "NotEqualTo",
            ]
        }
    },
}