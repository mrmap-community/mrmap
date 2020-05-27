"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 20.05.20

"""
from django.db.models import QuerySet

from MrMap.settings import XML_NAMESPACES
from csw.settings import CSW_CAPABILITIES_CONF
from csw.utils.converter import MetadataConverter
from csw.utils.csw_filter import *
from csw.utils.parameter import ParameterResolver, VERSION_CHOICES
from service.helper import xml_helper
from service.models import Metadata


class RequestResolver:
    """ Resolves which type of request has to be performed.

    """

    def __init__(self, param: ParameterResolver):
        self.param = param

        self.operation_resolver_map = {
            "GetRecords": GetRecordsResolver,
            "GetRecordById": GetRecordsByIdResolver,
            "GetCapabilities": GetCapabilitiesResolver,
            "DescribeRecord": None,
            "GetDomain": None,
            "Transaction": None,
            "Harvest": None,
        }

        self.attribute_map = {
            "dc:title": "title",
            "dc:identifier": "identifier",
            "dc:abstract": "abstract",
            "dc:description": "abstract",
            "dc:date": "created",
            "dc:modified": "last_modified",
        }

    def get_response(self):
        """ Resolve the corresponding class to perform the response fetching

        Returns:

        """
        request = self.param.request

        resolver_class = self.operation_resolver_map.get(request, None)
        if not resolver_class:
            raise ValueError(
                "No valid operation or operation not supported. Supported operations are `{}`".format(
                    ", ".join(key for key, val in self.operation_resolver_map.items() if val is not None)
                ),
                "request"
            )
        if self.param.version not in VERSION_CHOICES:
            raise ValueError(
                "{} is not supported. Choices are '{}'".format(self.param.version, ", ".join(VERSION_CHOICES)),
                "version"
            )

        class_obj = resolver_class(param=self.param)
        response = class_obj.get_response()
        return response

    def get_metadata(self, filtered: bool, sorted: bool):
        """ Returns available metadata

        Args:
            filtered (bool): Whether to apply given constraint filtering or not
        Returns:

        """
        all_md = Metadata.objects.filter(
            is_active=True
        )
        if filtered:
            all_md = self._filter_metadata(all_md)
        if sorted:
            all_md = self._sort_metadata(all_md)
        return all_md

    def _filter_metadata(self, all_md: QuerySet):
        """ Perform filtering using constraint parameter

        Args:
            all_md (QuerySet): The unfiltered metadata queryset
        Returns:
             all_md (QuerySet): The filtered metadata queryset
        """
        if self.param.constraint is None:
            return all_md
        filtered_md = filter_queryset(self.param.constraint, self.param.constraint_language, all_md)
        return filtered_md

    def _sort_metadata(self, all_md: QuerySet):
        """ Perform sorting using sortBy parameter

        Values follow the syntax of `attribute:A|D`. The A or D indicates ASC or DESC ordering. Since the
        attribute can contain `:` as well, the A|D part has to be separated without the attribute to be damaged.

        Args:
            all_md (QuerySet): The unsorted metadata queryset
        Returns:
             all_md (QuerySet): The sorted metadata queryset
        """
        if self.param.sort_by is None:
            return all_md
        sort_by_components = self.param.sort_by.split(":")
        attrib = ":".join(sort_by_components[:-1])
        md_attrib = self.attribute_map.get(attrib, None)
        if md_attrib is None:
            raise NotImplementedError(
                "{} not supported for sorting".format(attrib),
                "sortBy"
            )
        desc = sort_by_components[-1] == "D"
        if desc:
            md_attrib = "-" + md_attrib
        return all_md.order_by(md_attrib)


class GetRecordsResolver(RequestResolver):
    def __init__(self, param: ParameterResolver):
        super().__init__(param=param)

    def get_response(self):
        """ Creates the xml response

        Returns:
             xml_str (str): The response as string
        """
        metadata = self.get_metadata(
            filtered=True,
            sorted=True
        )
        i_from = self.param.start_position - 1
        i_to = i_from + self.param.max_records
        returned_metadata = metadata[i_from:i_to]
        if i_from > metadata.count():
            raise ValueError("Start position ({}) can't be greater than number of matching records ({})".format(self.param.start_position, metadata.count()), "startPosition")

        # Only return results content if this was requested
        md_converter = MetadataConverter(self.param, metadata, returned_metadata)
        response = md_converter.create_xml_response(with_content=self.param.result_type == "results")

        xml_str = xml_helper.xml_to_string(response, pretty_print=True)
        return xml_str


class GetRecordsByIdResolver(RequestResolver):
    def __init__(self, param: ParameterResolver):
        super().__init__(param=param)

    def get_response(self):
        """ Creates the xml response

        Returns:
             xml_str (str): The response as string
        """
        metadata = self.get_metadata(
            filtered=True,
            sorted=True
        ).filter(
            identifier__in=self.param.request_id.split(","),
        )
        i_from = self.param.start_position - 1
        i_to = i_from + self.param.max_records
        returned_metadata = metadata[i_from:i_to]
        if i_from > metadata.count():
            raise ValueError("Start position ({}) can't be greater than number of matching records ({})".format(self.param.start_position, metadata.count()), "startPosition")

        md_converter = MetadataConverter(self.param, metadata, returned_metadata)
        response = md_converter.create_xml_response(with_content=True)

        xml_str = xml_helper.xml_to_string(response, pretty_print=True)
        return xml_str

class GetCapabilitiesResolver(RequestResolver):
    def __init__(self, param: ParameterResolver):
        super().__init__(param=param)

        self.namespaces = {
            "csw": "http://www.opengis.net/cat/csw/2.0.2",
            "ogc": XML_NAMESPACES["ogc"],
            "gml": XML_NAMESPACES["gml"],
            "ows": XML_NAMESPACES["ows"],
            "xlink": XML_NAMESPACES["xlink"],
            "inspire_ds": XML_NAMESPACES["inspire_ds"],
            "inspire_com": XML_NAMESPACES["inspire_com"],
            "xsi": XML_NAMESPACES["xsi"],
        }

        self.csw_ns = "{" + self.namespaces["csw"] + "}"
        self.xsi_ns = "{" + self.namespaces["xsi"] + "}"
        self.ows_ns = "{" + self.namespaces["ows"] + "}"
        self.xlink_ns = "{" + self.namespaces["xlink"] + "}"

    def get_response(self):
        """ Creates the xml response

        Returns:
             xml_str (str): The response as string
        """
        response = self._create_csw_capabilities()
        xml_str = xml_helper.xml_to_string(response, pretty_print=True)
        return xml_str

    def _create_csw_capabilities(self):
        root = Element(
            "{}Capabilities".format(self.csw_ns),
            attrib={
                "version": "2.0.2",
                "{}schemaLocation".format(self.xsi_ns): "http://www.opengis.net/cat/csw/2.0.2",
            },
            nsmap=self.namespaces
        )
        # ToDo: Reduce the output based on requested section parameter?

        self._create_csw_service_identification(root)
        self._create_csw_service_provider(root)
        self._create_csw_operations_metadata(root)

        return root

    def _create_csw_service_identification(self, root: Element):
        """ Creates the <ows:ServiceIdentification> element

        Returns:

        """
        elem = xml_helper.create_subelement(
            root,
            "{}ServiceIdentification".format(self.ows_ns)
        )

        service_identification = CSW_CAPABILITIES_CONF.get("service_identification")

        # Title
        xml_helper.create_subelement(elem, "{}Title".format(self.ows_ns)).text = service_identification.get("title", "")

        # Abstract
        xml_helper.create_subelement(elem, "{}Abstract".format(self.ows_ns)).text = service_identification.get("abstract", "")

        # Keywords
        kw_elem = xml_helper.create_subelement(elem, "{}Keywords".format(self.ows_ns))
        keywords = service_identification.get("keywords", "").split(",")
        for kw in keywords:
            xml_helper.create_subelement(kw_elem, "{}Keyword".format(self.ows_ns)).text = kw

        # ServiceType
        xml_helper.create_subelement(elem, "{}ServiceType".format(self.ows_ns)).text = service_identification.get("service_type", "")

        # ServiceTypeVersion
        xml_helper.create_subelement(elem, "{}ServiceTypeVersion".format(self.ows_ns)).text = service_identification.get("service_type_version", "")

        # Fees
        xml_helper.create_subelement(elem, "{}Fees".format(self.ows_ns)).text = service_identification.get("fees", "")

        # AccessConstraints
        xml_helper.create_subelement(elem, "{}AccessConstraints".format(self.ows_ns)).text = service_identification.get("access_constraints", "")

    def _create_csw_service_provider(self, root: Element):
        """ Creates the <ows:ServiceProvider> element

        Returns:

        """
        elem = xml_helper.create_subelement(
            root,
            "{}ServiceProvider".format(self.ows_ns)
        )

        service_provider = CSW_CAPABILITIES_CONF.get("service_provider")

        # ProviderName
        xml_helper.create_subelement(elem, "{}ProviderName".format(self.ows_ns)).text = service_provider.get("name", "")

        # ProviderSite
        xml_helper.create_subelement(elem, "{}ProviderSite".format(self.ows_ns), attrib={"{}href".format(self.xlink_ns): service_provider.get("provider_site")})

        # ServiceContact
        contact_elem = xml_helper.create_subelement(elem, "{}ServiceContact".format(self.ows_ns))

        ## IndividualName
        xml_helper.create_subelement(contact_elem, "{}IndividualName".format(self.ows_ns)).text = service_provider.get("individual_name", "")

        ## PositionName
        xml_helper.create_subelement(contact_elem, "{}PositionName".format(self.ows_ns)).text = service_provider.get("position_name", "")

        ## ContactInfo
        contact_info_elem = xml_helper.create_subelement(contact_elem, "{}ContactInfo".format(self.ows_ns))

        ### Phone
        phone_elem = xml_helper.create_subelement(contact_info_elem, "{}Phone".format(self.ows_ns))

        #### Voice
        xml_helper.create_subelement(phone_elem, "{}Voice".format(self.ows_ns)).text = service_provider.get("contact_phone", "")

        #### Facsimile
        xml_helper.create_subelement(phone_elem, "{}Facsimile".format(self.ows_ns)).text = service_provider.get("contact_facsimile", "")

        ### Address
        address_elem = xml_helper.create_subelement(contact_info_elem, "{}Address".format(self.ows_ns))

        #### DeliveryPoint
        xml_helper.create_subelement(address_elem, "{}DeliveryPoint".format(self.ows_ns)).text = service_provider.get("contact_address_delivery_point", "")

        #### City
        xml_helper.create_subelement(address_elem, "{}City".format(self.ows_ns)).text = service_provider.get("contact_address_city", "")

        #### AdministrativeArea
        xml_helper.create_subelement(address_elem, "{}AdministrativeArea".format(self.ows_ns)).text = service_provider.get("contact_address_administrative_area", "")

        #### PostalCode
        xml_helper.create_subelement(address_elem, "{}PostalCode".format(self.ows_ns)).text = service_provider.get("contact_address_postal_code", "")

        #### Country
        xml_helper.create_subelement(address_elem, "{}Country".format(self.ows_ns)).text = service_provider.get("contact_address_country", "")

        #### ElectronicMailAddress
        xml_helper.create_subelement(address_elem, "{}ElectronicMailAddress".format(self.ows_ns)).text = service_provider.get("contact_address_email", "")

    def _create_csw_operations_metadata(self, root: Element):
        """ Creates the <ows:OperationsMetadata> element

        Returns:

        """
        elem = xml_helper.create_subelement(
            root,
            "{}OperationsMetadata".format(self.ows_ns)
        )
        operations_metadata = CSW_CAPABILITIES_CONF.get("operations_metadata", {})
        operations = operations_metadata.get("operations", {})

        for operation_name, operation_val  in operations.items():
            operation_elem = xml_helper.create_subelement(elem, "{}Operation".format(self.ows_ns), attrib={
                "name": operation_name
            })
            # DCP | HTTP
            dcp_elem = xml_helper.create_subelement(operation_elem, "{}DCP".format(self.ows_ns))
            http_elem = xml_helper.create_subelement(dcp_elem, "{}HTTP".format(self.ows_ns))

            ## Get
            xml_helper.create_subelement(http_elem, "{}Get".format(self.ows_ns), attrib={
                "{}href".format(self.xlink_ns): operation_val.get("get_uri")
            })

            ## Post
            xml_helper.create_subelement(http_elem, "{}Post".format(self.ows_ns), attrib={
                "{}href".format(self.xlink_ns): operation_val.get("post_uri")
            })

            # Parameter
            parameters = operation_val.get("parameter", {})
            for param_key, param_val in parameters.items():
                param_elem = xml_helper.create_subelement(operation_elem, "{}Parameter".format(self.ows_ns), attrib={
                    "name": param_key
                })
                for val in param_val:
                    xml_helper.create_subelement(param_elem, "{}Value".format(self.ows_ns)).text = val

            # Constraint
            constraints = operation_val.get("constraint", {})
            for cons_key, cons_val in constraints.items():
                cons_elem = xml_helper.create_subelement(operation_elem, "{}Constraint".format(self.ows_ns), attrib={
                    "name": cons_key
                })
                for val in cons_val:
                    xml_helper.create_subelement(cons_elem, "{}Value".format(self.ows_ns)).text = val
