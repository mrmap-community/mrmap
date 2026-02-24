from lxml import etree
from registry.enums.service import (HttpMethodEnum, OGCOperationEnum,
                                    OGCServiceVersionEnum)
from registry.models.service import CatalogueService
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

        self.add_child_element(
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
            sort = self.add_child_element(query, "SortBy")
            self._build_sort(sort, sort_by)

        if constraint and constraint_language == "CQL_TEXT":
            self._build_cql_filter(query, constraint)
        elif constraint and constraint_language == "FILTER":
            self._build_fes_filter(query, constraint)

        return root

    def _build_element_set_name(self, parent, value="summary"):
        esn = self.add_child_element(
            parent,
            "ElementSetName",
            text=value
        )
        return esn

    def _build_query(self, root, type_names):
        query_el = self.add_child_element(
            root,
            "Query",
            attributes={
                "typeNames": " ".join(type_names),
            },
        )
        return query_el

    def _build_cql_filter(self, query_el, cql_text):
        constraint = self.add_child_element(
            query_el,
            "Constraint",
            attributes={"version": "1.1.0"},
        )

        self.add_foreign_child(
            constraint,
            etree.QName(NAMESPACE_LOOKUP["csw_2_0_2"], "CqlText"),
            text=cql_text,
        )

    def _build_fes_filter(self, query_el, filter_xml):
        constraint = self.add_child_element(
            query_el,
            "Constraint",
            attributes={"version": "1.1.0"},
        )

        self.add_foreign_child(
            constraint,
            etree.QName(NAMESPACE_LOOKUP["ogc"], "Filter"),
            text=filter_xml,
        )

    def add_bbox_constraint(self, query, bbox):
        minx, miny, maxx, maxy = bbox.split(",")

        constraint = self.add_child_element(
            query,
            "Constraint",
            attributes={"version": "1.1.0"},
        )

        filt = self.add_foreign_child(
            constraint,
            etree.QName(NAMESPACE_LOOKUP["ogc"], "Filter"),
        )

        bbox_el = self.add_foreign_child(
            filt,
            etree.QName(NAMESPACE_LOOKUP["ogc"], "BBOX"),
        )

        self.add_foreign_child(
            bbox_el,
            etree.QName(NAMESPACE_LOOKUP["ogc"], "PropertyName"),
            text="ows:BoundingBox",
        )

        env = self.add_foreign_child(
            bbox_el,
            etree.QName(NAMESPACE_LOOKUP["gml_3_1_1"], "Envelope"),
            attributes={"srsName": "EPSG:4326"},
        )

        self.add_foreign_child(env, etree.QName(
            NAMESPACE_LOOKUP["gml_3_1_1"], "lowerCorner"), f"{minx} {miny}")
        self.add_foreign_child(env, etree.QName(
            NAMESPACE_LOOKUP["gml_3_1_1"], "upperCorner"), f"{maxx} {maxy}")

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
                etree.QName(NAMESPACE_LOOKUP["ogc"], "SortProperty"),
            )
            self.add_foreign_child(
                sp,
                etree.QName(NAMESPACE_LOOKUP["ogc"], "PropertyName"),
                text=prop,
            )
            self.add_foreign_child(
                sp,
                etree.QName(NAMESPACE_LOOKUP["ogc"], "SortOrder"),
                text=order,
            )


class CSWCapabilities(XMLBuilder):
    NSMAP = {
        "ows": NAMESPACE_LOOKUP["ows"],
        "csw": NAMESPACE_LOOKUP["csw_2_0_2"],
        "ogc": NAMESPACE_LOOKUP["ogc"],
        "xlink": NAMESPACE_LOOKUP["xlink"],
    }

    def __init__(
        self,
        csw: CatalogueService,
        extra_keywords: list[str] = None,
        base_url: str = None,
    ):
        self.csw = csw
        self.extra_keywords = extra_keywords or []
        self.base_url = base_url

    def to_xml(self):
        root = etree.Element(
            etree.QName(self.NSMAP["csw"], "Capabilities"),
            nsmap=self.NSMAP,
            version=str(OGCServiceVersionEnum(self.csw.version).label),
        )

        self._build_service_identification(root)
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
        keywords = self._get_keywords()
        if keywords:
            kw = self.el(self.NSMAP["ows"], "Keywords", si)
            for k in keywords:
                self.el(self.NSMAP["ows"], "Keyword", kw, text=k)

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

    # -----------------------------------

    def _build_filter_capabilities(self, root):
        self.el(self.NSMAP["ogc"], "Filter_Capabilities", parent=root)
