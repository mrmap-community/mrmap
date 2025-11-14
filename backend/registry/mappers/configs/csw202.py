from registry.mappers.namespaces import (CSW_2_0_2_NAMESPACE, OWS_NAMESPACE,
                                         XLINK_NAMESPACE)

XPATH_MAP = {
    # (Service-Klasse, Version) -> Mapping Feldname -> XPath
    ("CSW", "2.0.2"): {
        "_namespaces": {
            "xlink": XLINK_NAMESPACE,
            "csw": CSW_2_0_2_NAMESPACE,
            "ows": OWS_NAMESPACE,
        },
        "_schema": "http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd",
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
                "service_contact": {
                    "_model": "registry.MetadataContact",
                    "_base_xpath": "/csw:Capabilities/ows:ServiceProvider",
                    "_create_mode": "get_or_create",
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
                    "_base_xpath": "/csw:Capabilities/ows:ServiceProvider",
                    "_create_mode": "get_or_create",
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
                    "_base_xpath": "/csw:Capabilities/ows:OperationsMetadata/ows:Operation/ows:DCP/ows:HTTP//ows:*",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "method": {
                            "_inputs": (".",),
                            "_parser": "registry.mappers.parsers.value.method_to_enum",
                            "_reverse_parser": "registry.mappers.parsers.value.enum_to_method",
                        },
                        "operation": {
                            "_inputs": ("../../../@name",),
                            "_parser": "registry.mappers.parsers.value.operation_to_enum",
                            "_reverse_parser": "registry.mappers.parsers.value.enum_to_operation"
                        },
                        "url": "./@xlink:href",
                        "mime_types": {
                            "_model": "registry.MimeType",
                            "_base_xpath": '../../../ows:Parameter[@name="outputFormat"]/ows:Value',
                            "_create_mode": "get_or_create",
                            "_many": True,
                            "fields": {
                                "mime_type": "."
                            }
                        }
                    }
                },
                "keywords": {
                    "_model": "registry.Keyword",
                    "_base_xpath": "/csw:Capabilities/ows:ServiceIdentification/ows:Keywords/ows:Keyword",
                    "_create_mode": "get_or_create",
                    "_many": True,
                    "fields": {
                        "keyword": "./."
                    }
                },

                # TODO: model has no fk to the layer/service objects.
                # Use _parser or redesign model
                # "remote_metadata": {
                #     "_model": "registry.RemoteMetadata",
                #     "_base_xpath": "./wms:MetadataURL/wms:OnlineResource",
                #     "fields": {
                #         "link": "./@xlink:href"
                #     }
                # },
            }
        }
    },
}
