from registry.mappers.namespaces import (GCO_NAMESPACE, GMD_NAMESPACE,
                                         SRV_NAMESPACE)

XPATH_MAP = {
    ("ISO", "Dataset"): {
        "_namespaces": {
            "gmd": GMD_NAMESPACE,
            "gco": GCO_NAMESPACE,
            "srv": SRV_NAMESPACE,
        },
        "_schema": "http://www.isotc211.org/2005/gmd",
        "_pre_save": [
        ],
        "dataset": {
            "_model": "registry.DatasetMetadataRecord",
            "_base_xpath": "/gmd:MD_Metadata",
            "fields": {
                "title": "",
                "abstract": "",
                "code": "",
                "code_space": "",
                "date_stamp": "",

                "bounding_geometry": "",
                "spatial_res_type": "",
                "spatial_res_value": "",
                "keywords": {

                },
                "file_identifier": "gmd:fileIdentifier/gco:CharacterString",
                "metadata_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier",
                    "_create_mode": "get_or_create",
                    "fields": {
                        # "name": "./ows:ProviderName",
                        # "person_name": "./ows:ServiceContact/ows:IndividualName",
                        # "phone": "./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Voice",
                        # "facsimile": "./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Facsimile",
                        # "email": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:ElectronicMailAddress",
                        # "country": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:Country",
                        # "postal_code": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:PostalCode",
                        # "city": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:City",
                        # "state_or_province": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:AdministrativeArea",
                        # "address": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:DeliveryPoint"
                    }
                },
                "reference_systems": {
                    "_model": "registry.ReferenceSystem",
                    "_base_xpath": "./gmd:referenceSystemInfo/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier/gmd:RS_Identifier",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "_parser": "registry.mappers.parsers.wfs.parse_reference_systems",
                },
            }
        }
    },
}
