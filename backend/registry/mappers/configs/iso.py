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
                "title": "./gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString",
                "abstract": "./gmd:abstract/gco:CharacterString",
                "access_constraints": "./gmd:resourceConstraints/gmd:MD_LegalConstraints[gmd:accessConstraints/gmd:MD_RestrictionCode/@codeListValue=\"otherRestrictions\"]/gmd:otherConstraints/gco:CharacterString",
                "code": "",
                "code_space": "",
                # TODO: maybe parser is needed to convert simple Date information to DateTime
                "date_stamp": "./gmd:dateStamp/*[self::gco:DateTime or self::gco:Date]",
                "bounding_geometry": "",
                "spatial_res_type": "",
                "spatial_res_value": "",
                "file_identifier": "./gmd:fileIdentifier/gco:CharacterString",
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "./gmd:descriptiveKeywords/gmd:MD_Keywords/gmd:keyword",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                      "keyword": "./gco:CharacterString"
                    }

                },
                "dataset_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./gmd:pointOfContact/gmd:CI_ResponsibleParty",
                    "_create_mode": "get_or_create",
                    "fields": {
                        "name": "./gmd:organisationName/gco:CharacterString",
                        "person_name": "./gmd:individualName/gco:CharacterString",
                        "phone": "./gmd:contactInfo/gmd:CI_Contact/gmd:phone/gmd:CI_Telephone/gmd:voice/gco:CharacterString",
                        "email": "./gmd:contactInfo/gmd:CI_Contact/gmd:address/gmd:CI_Address/gmd:electronicMailAddress/gco:CharacterString",
                    }
                },
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
