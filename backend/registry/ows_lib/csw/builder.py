from lxml import etree
from registry.enums.service import (HttpMethodEnum, OGCOperationEnum,
                                    OGCServiceVersionEnum)
from registry.ows_lib.xml.builder import XMLBuilder, XSDSkeletonBuilder
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP


class CSWBuilder(XSDSkeletonBuilder):
    def __init__(self, service_version="2.0.2"):
        super().__init__(("csw", "discovery", service_version))
        self.service_version = service_version

    def transform_operation_urls(self, operation_urls):
        transformed_operations = []
        for name, operation_url in operation_urls.items():
            operation = {
                "_attributes": {"name": name},
                "DCP": {
                    "HTTP": {
                        method.capitalize(): {
                            "_attributes": {"xlink:href": operation_url["href"]}
                        }
                        for method in operation_url.get("methods", [])
                    }
                },
            }
            if "parameters" in operation_url:
                operation["Parameters"] = {
                    "Parameter": {
                        "_attributes": {"name": operation_url["parameters"]["name"]},
                        "Value": [{"_text": v} for v in operation_url["parameters"]["values"]]
                    }
                }
            transformed_operations.append(operation)
        return transformed_operations

    def build_capabilities(
        self,
        title,
        abstract,
        operation_urls,
        keywords=None,
    ):
        keywords = keywords or []
        transformed_operations = self.transform_operation_urls(operation_urls)

        children_attrs = {
            "ServiceIdentification": {
                "Title": {"_text": title},
                "Abstract": {"_text": abstract},
                "ServiceType": {"_text": "CSW"},
                "ServiceTypeVersion": {"_text": self.service_version},
                "Keywords": {"Keyword": [{"_text": k} for k in keywords]} if keywords else None
            },
            "OperationsMetadata": {
                "Operation": transformed_operations
            }
        }
        root = self.build_element(
            "Capabilities",
            children_attributes=children_attrs
        )
        return root

    def build_get_record_by_id(
        self,
        ids,
        element_set_name="summary",
    ):
        root = self.build_element(
            "GetRecordById",
            attributes={
                "service": "CSW",
                "version": "2.0.2",
            },
        )

        self.add_foreign_child(
            root,
            "Id",
            text=",".join(ids),
        )

        self._build_element_set_name(root, element_set_name)

        return root

    def build_get_records(
        self,
        *,
        type_names=("csw:Record",),
        result_type="hits",
        element_set="summary",
        sort_by=None,
        constraint=None,
        constraint_language=None,
    ):
        root = self.build_element(
            "GetRecords",
            attributes={
                "service": "CSW",
                "version": "2.0.2",
                "resultType": result_type,
            },
        )
        query = self._build_query(root, type_names)
        self._build_element_set_name(query, element_set)

        if sort_by:
            sort = self.add_foreign_child(
                query,
                NAMESPACE_LOOKUP["csw_2_0_2"],
                "SortBy"
            )
            self._build_sort(sort, sort_by)

        if constraint and constraint_language == "CQL_TEXT":
            self._build_cql_filter(query, constraint)
        elif constraint and constraint_language == "FILTER":
            self._build_fes_filter(query, constraint)

        return root

    def build_get_records_response(
        self,
        total_records,
        records_returned,
        version="2.0.2",
        next_record=None,
        record_schema="http://www.isotc211.org/2005/gmd",
        element_set="full",
        result_set_id=None,
        expires=None,
        time_stamp=None,
        csw_records=None,
        gmd_records=None,
    ):
        children_attrs = {
            "SearchStatus": {
                "_attributes": {"timestamp": time_stamp.isoformat() if time_stamp else None}
            },
            "SearchResults": {
                "_attributes": {
                    "numberOfRecordsMatched": total_records,
                    "numberOfRecordsReturned": records_returned,
                    "nextRecord": next_record,
                    "recordSchema": record_schema,
                    "elementSetName": element_set,
                    "resultSetId": result_set_id,
                    "expires": expires.isoformat() if expires else None,
                }
            }
        }

        root = self.build_element(
            "GetRecordsResponse",
            attributes={
                "version": version,
                "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation":
                    "http://www.opengis.net/cat/csw/2.0.2 http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd"
            },
            children_attributes=children_attrs
        )
        if csw_records:
            search_results_el = root.find(".//{*}SearchResults")
            for md in csw_records:
                search_results_el.append(md)
        # Append pre-built MD_Metadata elements directly
        if gmd_records:
            search_results_el = root.find(".//{*}SearchResults")
            for md in gmd_records:
                search_results_el.append(md)

        return root

    def build_get_records_by_id_response(
            self,
            gmd_records):
        children_attrs = {
            "{http://www.isotc211.org/2005/gmd}MD_Metadata": gmd_records or []
        }
        root = self.build_element(
            "GetRecordByIdResponse",
            attributes={
                "version": "2.0.2",
                "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation":
                    "http://www.opengis.net/cat/csw/2.0.2 http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd"
            },
            children_attributes=children_attrs
        )
        return root

    def _build_element_set_name(self, parent, value="summary"):
        esn = self.add_foreign_child(
            parent,
            NAMESPACE_LOOKUP["csw_2_0_2"],
            "ElementSetName",
            text=value
        )
        return esn

    def _build_query(self, root, type_names):
        query_el = self.add_foreign_child(
            root,
            NAMESPACE_LOOKUP["csw_2_0_2"],
            "Query",
            attributes={
                "typeNames": " ".join(type_names),
            },
        )
        return query_el

    def _build_cql_filter(self, query_el, cql_text):
        constraint = self.add_foreign_child(
            query_el,
            NAMESPACE_LOOKUP["csw_2_0_2"],
            "Constraint",
            attributes={"version": "1.1.0"},
        )

        self.add_foreign_child(
            constraint,
            NAMESPACE_LOOKUP["csw_2_0_2"],
            "CqlText",
            text=cql_text,
        )

    def _build_fes_filter(self, query_el, filter_xml):
        constraint = self.add_foreign_child(
            query_el,
            NAMESPACE_LOOKUP["csw_2_0_2"],
            "Constraint",
            attributes={"version": "1.1.0"},
        )

        self.add_foreign_child(
            constraint,
            NAMESPACE_LOOKUP["ogc"],
            "Filter",
            text=filter_xml,
        )

    def add_bbox_constraint(self, query, bbox):
        minx, miny, maxx, maxy = bbox.split(",")

        constraint = self.add_foreign_child(
            query,
            NAMESPACE_LOOKUP["csw_2_0_2"],
            "Constraint",
            attributes={"version": "1.1.0"},
        )

        filt = self.add_foreign_child(
            constraint,
            NAMESPACE_LOOKUP["ogc"],
            "Filter",
        )

        bbox_el = self.add_foreign_child(
            filt,
            NAMESPACE_LOOKUP["ogc"],
            "BBOX",
        )

        self.add_foreign_child(
            bbox_el,
            NAMESPACE_LOOKUP["ogc"],
            "PropertyName",
            text="ows:BoundingBox",
        )

        env = self.add_foreign_child(
            bbox_el,
            NAMESPACE_LOOKUP["gml_3_1_1"],
            "Envelope",
            attributes={"srsName": "EPSG:4326"},
        )

        self.add_foreign_child(
            env, NAMESPACE_LOOKUP["gml_3_1_1"], "lowerCorner", text=f"{minx} {miny}")
        self.add_foreign_child(
            env, NAMESPACE_LOOKUP["gml_3_1_1"], "upperCorner", text=f"{maxx} {maxy}")

    def _build_sort(self, sort_el, sort_by):
        """
        sort_by = [
            ("dc:title", "ASC"),
            ("dc:date", "DESC"),
        ]
        """
        for prop, order in sort_by:
            sp = self.add_foreign_child(
                sort_el,
                NAMESPACE_LOOKUP["ogc"],
                "SortProperty",
            )
            self.add_foreign_child(
                sp,
                NAMESPACE_LOOKUP["ogc"],
                "PropertyName",
                text=prop,
            )
            self.add_foreign_child(
                sp,
                NAMESPACE_LOOKUP["ogc"],
                "SortOrder",
                text=order,
            )

    def build_acknowledgement(self, timestamp, request_id=None, echoed_request=None):
        root = self.build_element(
            "Acknowledgement",
            attributes={
                "timestamp": timestamp.isoformat(),
            },
        )

        if request_id:
            self.add_foreign_child(
                root,
                NAMESPACE_LOOKUP["csw_2_0_2"],
                "RequestId",
                text=request_id,
            )

        if echoed_request:
            echo_el = self.add_foreign_child(
                root,
                NAMESPACE_LOOKUP["csw_2_0_2"],
                "EchoedRequest",
            )
            echo_el.append(echoed_request)

        return root


class CSWCapabilities(XMLBuilder):
    NSMAP = {
        "ows": NAMESPACE_LOOKUP["ows"],
        "csw": NAMESPACE_LOOKUP["csw_2_0_2"],
        "ogc": NAMESPACE_LOOKUP["ogc"],
        "xlink": NAMESPACE_LOOKUP["xlink"],
    }

    def __init__(
        self,
        csw,
        extra_keywords: list[str] = None,
        base_url: str = None,
        operation_parameters: dict = None,
        filter_capabilities: dict = None,
    ):
        self.csw = csw
        self.extra_keywords = extra_keywords or []
        self.base_url = base_url
        self.operation_parameters = operation_parameters or {}
        self.filter_capabilities = filter_capabilities or {}

    def to_xml(self):
        root = etree.Element(
            etree.QName(self.NSMAP["csw"], "Capabilities"),
            nsmap=self.NSMAP,
            version=str(OGCServiceVersionEnum(self.csw.version).label),
        )

        self._build_service_identification(root)
        self._build_service_provider(root)
        self._build_operations_metadata(root)
        self._build_filter_capabilities(root)

        return root

    def to_xml_string(self):
        return etree.tostring(
            self.to_xml(),
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8"
        ).decode("utf-8")

    def _get_keywords(self):
        # existing persisted keywords (if any)
        persisted = [kw.keyword for kw in self.csw.keywords.all()]

        # merge with runtime keywords
        return list(set(persisted + self.extra_keywords))

    def _get_operation_url(self):
        return self.base_url

    # -----------------------------------

    def _build_service_identification(self, root):
        si = self.el(self.NSMAP["ows"], "ServiceIdentification", parent=root)

        self.el(self.NSMAP["ows"], "Title", si, text=self.csw.title)
        self.el(self.NSMAP["ows"], "Abstract", si, text=self.csw.abstract)
        self.el(self.NSMAP["ows"], "ServiceType", si, text="CSW")
        self.el(self.NSMAP["ows"], "ServiceTypeVersion",
                si, text=str(OGCServiceVersionEnum(self.csw.version).label))
        self.el(self.NSMAP["ows"], "Fees", si, text=self.csw.fees or "None")
        self.el(self.NSMAP["ows"], "AccessConstraints", si,
                text=self.csw.access_constraints or "None")
        keywords = self._get_keywords()
        if keywords:
            kw = self.el(self.NSMAP["ows"], "Keywords", si)
            for k in keywords:
                self.el(self.NSMAP["ows"], "Keyword", kw, text=k)

    # -----------------------------------

    def _build_service_provider(self, root):

        sp = self.el(self.NSMAP["ows"], "ServiceProvider", parent=root)

        self.el(self.NSMAP["ows"], "ProviderName", sp,
                text=self.csw.service_contact.name)

        sc = self.el(self.NSMAP["ows"], "ServiceContact", parent=sp)
        self.el(self.NSMAP["ows"], "IndividualName", sc,
                text=self.csw.service_contact.person_name) if self.csw.service_contact.person_name else None

        ci = self.el(self.NSMAP["ows"], "ContactInfo", parent=sc)

        phone = self.el(self.NSMAP["ows"], "Phone", parent=ci)
        self.el(self.NSMAP["ows"], "Voice", phone,
                text=self.csw.service_contact.phone) if self.csw.service_contact.phone else None
        self.el(self.NSMAP["ows"], "Facsimile", phone,
                text=self.csw.service_contact.facsimile) if self.csw.service_contact.facsimile else None

        address = self.el(self.NSMAP["ows"], "Address", parent=ci)
        self.el(self.NSMAP["ows"], "DeliveryPoint", address,
                text=self.csw.service_contact.address) if self.csw.service_contact.address else None
        self.el(self.NSMAP["ows"], "City", address,
                text=self.csw.service_contact.city) if self.csw.service_contact.city else None
        self.el(self.NSMAP["ows"], "PostalCode", address,
                text=self.csw.service_contact.postal_code) if self.csw.service_contact.postal_code else None
        self.el(self.NSMAP["ows"], "PostalCode", address,
                text=self.csw.service_contact.postal_code) if self.csw.service_contact.postal_code else None
        self.el(self.NSMAP["ows"], "Country", address,
                text=self.csw.service_contact.country) if self.csw.service_contact.country else None
        self.el(self.NSMAP["ows"], "ElectronicMailAddress", address,
                text=self.csw.service_contact.email) if self.csw.service_contact.email else None

    # -----------------------------------

    def _build_operations_metadata(self, root):
        ops_meta = self.el(self.NSMAP["ows"],
                           "OperationsMetadata", parent=root)
        operation_urls = self.csw.operation_urls.all()
        for op in operation_urls:
            name = str(OGCOperationEnum(op.operation).label)
            method = str(HttpMethodEnum(op.method).label)

            op_el = self.el(self.NSMAP["ows"],
                            "Operation", ops_meta, name=name)

            dcp = self.el(self.NSMAP["ows"], "DCP", op_el)
            http = self.el(self.NSMAP["ows"], "HTTP", dcp)

            method_el = self.el(self.NSMAP["ows"], method, http)
            method_el.set(
                etree.QName(self.NSMAP["xlink"], "href"),
                self._get_operation_url() or op.url
            )
            if self.operation_parameters.get(name):
                params_el = self.el(self.NSMAP["ows"], "Parameters", op_el)
                for param_name, param_values in self.operation_parameters[name].items():
                    param_el = self.el(
                        self.NSMAP["ows"], "Parameter", params_el, name=param_name)
                    for v in param_values:
                        self.el(self.NSMAP["ows"], "Value", param_el, text=v)

    # -----------------------------------

    def _build_filter_capabilities(self, root):
        """
        example:  
        <ogc:Spatial_Capabilities>
            <ogc:GeometryOperands>
                <ogc:GeometryOperand>gml:Point</ogc:GeometryOperand>
                <ogc:GeometryOperand>gml:LineString</ogc:GeometryOperand>
                <ogc:GeometryOperand>gml:Polygon</ogc:GeometryOperand>
                <ogc:GeometryOperand>gml:Envelope</ogc:GeometryOperand>
            </ogc:GeometryOperands>
            <ogc:SpatialOperators>
                <ogc:SpatialOperator name="BBOX"/>
                <ogc:SpatialOperator name="Beyond"/>
                <ogc:SpatialOperator name="Contains"/>
                <ogc:SpatialOperator name="Crosses"/>
                <ogc:SpatialOperator name="Disjoint"/>
                <ogc:SpatialOperator name="DWithin"/>
                <ogc:SpatialOperator name="Equals"/>
                <ogc:SpatialOperator name="Intersects"/>
                <ogc:SpatialOperator name="Overlaps"/>
                <ogc:SpatialOperator name="Touches"/>
                <ogc:SpatialOperator name="Within"/>
            </ogc:SpatialOperators>
        </ogc:Spatial_Capabilities>
        <ogc:Scalar_Capabilities>
            <ogc:LogicalOperators/>
            <ogc:ComparisonOperators>
                <ogc:ComparisonOperator>Between</ogc:ComparisonOperator>
                <ogc:ComparisonOperator>EqualTo</ogc:ComparisonOperator>
                <ogc:ComparisonOperator>GreaterThan</ogc:ComparisonOperator>
                <ogc:ComparisonOperator>GreaterThanEqualTo</ogc:ComparisonOperator>
                <ogc:ComparisonOperator>LessThan</ogc:ComparisonOperator>
                <ogc:ComparisonOperator>LessThanEqualTo</ogc:ComparisonOperator>
                <ogc:ComparisonOperator>Like</ogc:ComparisonOperator>
                <ogc:ComparisonOperator>NotEqualTo</ogc:ComparisonOperator>
                <ogc:ComparisonOperator>NullCheck</ogc:ComparisonOperator>
            </ogc:ComparisonOperators>
            <ogc:ArithmeticOperators>
                <ogc:Functions>
                    <ogc:FunctionNames>
                        <ogc:FunctionName nArgs="1">length</ogc:FunctionName>
                        <ogc:FunctionName nArgs="1">lower</ogc:FunctionName>
                        <ogc:FunctionName nArgs="1">ltrim</ogc:FunctionName>
                        <ogc:FunctionName nArgs="1">rtrim</ogc:FunctionName>
                        <ogc:FunctionName nArgs="1">trim</ogc:FunctionName>
                        <ogc:FunctionName nArgs="1">upper</ogc:FunctionName>
                    </ogc:FunctionNames>
                </ogc:Functions>
            </ogc:ArithmeticOperators>
        </ogc:Scalar_Capabilities>

            self.filter_capabilities = {
                "Spatial_Capabilities": {
                    "GeometryOperands": [
                        {
                            "name": "GeometryOperand",
                            "text": "gml:Point"
                        },
                        {
                            "name": "GeometryOperand",
                            "text": "gml:LineString"
                        },
                        {
                            "name": "GeometryOperand",
                            "text": "gml:Polygon"
                        }
                    ],
                    "SpatialOperators": [
                        {
                            "name": "SpatialOperator",
                            "_name": "BBOX"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Contains"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Crosses"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Disjoint"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Equals"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Intersects"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Overlaps"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Touches"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Within"
                        }
                    ],
                },
                "Scalar_Capabilities": {
                    "LogicalOperators": [
                        {
                            "name": "LogicalOperator",
                            "text": "AND"
                        },
                        {
                            "name": "LogicalOperator",
                            "text": "OR"
                        },
                        {
                            "name": "LogicalOperator",
                            "text": "NOT"
                        }
                    ],

                    "ComparisonOperators": [
                        {
                            "name": "ComparisonOperator",
                            "text": "EqualTo"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "NotEqualTo"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "LessThan"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "GreaterThan"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "LessThanEqualTo"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "GreaterThanEqualTo"
                        }
                    ]
                }
            }
        )

        """
        filter_capabilities = self.el(
            self.NSMAP["ogc"], "Filter_Capabilities", parent=root)
        for fc_name, fc_content in self.filter_capabilities.items():
            fc_el = self.el(self.NSMAP["ogc"], fc_name, filter_capabilities)
            for content_name, content_items in fc_content.items():
                content_el = self.el(self.NSMAP["ogc"], content_name, fc_el)
                for item in content_items:
                    self.el(
                        self.NSMAP["ogc"],
                        item["name"],
                        content_el,
                        text=item.get("text"),
                        **({"name": item["_name"]} if "_name" in item else {})
                    )
