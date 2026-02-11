from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

XPATH_MAP = {
    # (Service-Klasse, Version) -> Mapping Feldname -> XPath
    ("CSW", "2.0.2"): {
        "_namespaces": {
            "xlink": NAMESPACE_LOOKUP["xlink"],
            "csw": NAMESPACE_LOOKUP["csw_2_0_2"],
            "ows": NAMESPACE_LOOKUP["ows"],
            "inspire_common": NAMESPACE_LOOKUP["inspire_common"],
        },
        "_schema": "http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd",
        "_pre_save": [
            "registry.mappers.extensions.clean_up_operation_urls"
        ],
        "service": {
            "_model": "registry.CatalogueService",
            "_base_xpath": "/csw:Capabilities",
            "fields": {
                "version":  {
                    "_inputs": ("./@version",),
                    "_parser": "registry.mappers.parsers.value.version_to_int",
                    "_reverse_parser": "registry.mappers.parsers.value.int_to_version"
                },
                "title": "./ows:ServiceIdentification/ows:Title",
                "abstract": "./ows:ServiceIdentification/ows:Abstract",
                "fees": "./ows:ServiceIdentification/ows:Fees",
                "access_constraints": "./ows:ServiceIdentification/ows:AccessConstraints",
                "remote_metadata": {
                    "_model": "registry.CatalogueServiceRemoteMetadata",
                    "_base_xpath": "./ows:OperationsMetadata/ows:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./ows:OperationsMetadata/ows:ExtendedCapabilities/inspire_common:MetadataUrl/inspire_common:URL/[text()='{link}']",
                        },
                    },
                    "fields": {
                        "link": "./."
                    }
                },
                "service_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./ows:ServiceProvider",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./ows:ServiceProvider",
                        },
                    },
                    "fields": {
                        "name": "./ows:ProviderName",
                        "person_name": "./ows:ServiceContact/ows:IndividualName",
                        "phone": "./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Voice",
                        "facsimile": "./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Facsimile",
                        "email": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:ElectronicMailAddress",
                        "country": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:Country",
                        "postal_code": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:PostalCode",
                        "city": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:City",
                        "state_or_province": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:AdministrativeArea",
                        "address": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:DeliveryPoint"
                    }
                },
                "metadata_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "./ows:ServiceProvider",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./ows:ServiceProvider",
                        },
                    },
                    "fields": {
                        "name": "./ows:ProviderName",
                        "person_name": "./ows:ServiceContact/ows:IndividualName",
                        "phone": "./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Voice",
                        "facsimile": "./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Facsimile",
                        "email": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:ElectronicMailAddress",
                        "country": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:Country",
                        "postal_code": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:PostalCode",
                        "city": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:City",
                        "state_or_province": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:AdministrativeArea",
                        "address": "./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:DeliveryPoint"
                    }
                },
                "operation_urls": {
                    "_model": "registry.CatalogueServiceOperationUrl",
                    "_base_xpath": "/csw:Capabilities/ows:OperationsMetadata/ows:Operation/ows:DCP/ows:HTTP//*[self::ows:Post or self::ows:Get]",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "compiler": "registry.mappers.identifiers.wfs_operation_url_identifier"
                        },
                    },
                    "fields": {
                        "method": {
                            "_inputs": (".",),
                            "_parser": "registry.mappers.parsers.value.method_to_enum",
                            "_reverse_parser": "registry.mappers.parsers.value.serialize_method",
                        },
                        "operation": {
                            "_inputs": ("../../../@name",),
                            "_parser": "registry.mappers.parsers.value.operation_to_enum",
                            "_reverse_parser": "registry.mappers.parsers.value.serialize_operation"
                        },
                        "url": "./@xlink:href",
                        "mime_types": {
                            "_model": "registry.MimeType",
                            "_base_xpath": '../../../ows:Parameter[@name="outputFormat"]/ows:Value',
                            "_create_mode": "get_or_create",
                            "fields": {
                                "mime_type": "."
                            }
                        }
                    }
                },
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "./ows:ServiceIdentification/ows:Keywords/ows:Keyword",
                    "_create_mode": "get_or_create",
                    "_reverse": {
                        "_identifier": {
                            "xpath": "./ows:ServiceIdentification/ows:Keywords/ows:Keyword[text()='{keyword}']",
                        },
                    },
                    "fields": {
                        "keyword": "./."
                    }
                },
            }
        }
    },
}
