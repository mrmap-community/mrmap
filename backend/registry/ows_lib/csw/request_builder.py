from lxml import etree
from registry.ows_lib.xml.builder import XSDSkeletonBuilder
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP


class CSWBuilder(XSDSkeletonBuilder):
    def __init__(self, service_version="2.0.2"):
        self.builder = XSDSkeletonBuilder(
            ("csw", "Exception", service_version)
        )

    def build_get_record_by_id(
        self,
        ids,
        element_set_name="summary",
    ):
        root = self.builder.build_element(
            "GetRecordById",
            attributes={
                "service": "CSW",
                "version": "2.0.2",
            },
        )

        self.builder.add_child_element(
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
        root = self.builder.build_element(
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
            sort = self.builder.add_child_element(query, "SortBy")
            self._build_sort(sort, sort_by)

        if constraint and constraint_language == "CQL_TEXT":
            self._build_cql_filter(query, constraint)
        elif constraint and constraint_language == "FILTER":
            self._build_fes_filter(query, constraint)

        return root

    def _build_element_set_name(self, parent, value="summary"):
        esn = self.builder.add_child_element(
            parent,
            "ElementSetName",
            text=value
        )
        return esn

    def _build_query(self, root, type_names):
        query_el = self.builder.add_child_element(
            root,
            "Query",
            attributes={
                "typeNames": " ".join(type_names),
            },
        )
        return query_el

    def _build_cql_filter(self, query_el, cql_text):
        constraint = self.builder.add_child_element(
            query_el,
            "Constraint",
            attributes={"version": "1.1.0"},
        )

        self.builder.add_foreign_child(
            constraint,
            etree.QName(NAMESPACE_LOOKUP["csw_2_0_2"], "CqlText"),
            text=cql_text,
        )

    def _build_fes_filter(self, query_el, filter_xml):
        constraint = self.builder.add_child_element(
            query_el,
            "Constraint",
            attributes={"version": "1.1.0"},
        )

        self.builder.add_foreign_child(
            constraint,
            etree.QName(NAMESPACE_LOOKUP["ogc"], "Filter"),
            text=filter_xml,
        )

    def add_bbox_constraint(self, query, bbox):
        minx, miny, maxx, maxy = bbox.split(",")

        constraint = self.builder.add_child_element(
            query,
            "Constraint",
            attributes={"version": "1.1.0"},
        )

        filt = self.builder.add_foreign_child(
            constraint,
            etree.QName(NAMESPACE_LOOKUP["ogc"], "Filter"),
        )

        bbox_el = self.builder.add_foreign_child(
            filt,
            etree.QName(NAMESPACE_LOOKUP["ogc"], "BBOX"),
        )

        self.builder.add_foreign_child(
            bbox_el,
            etree.QName(NAMESPACE_LOOKUP["ogc"], "PropertyName"),
            text="ows:BoundingBox",
        )

        env = self.builder.add_foreign_child(
            bbox_el,
            etree.QName(NAMESPACE_LOOKUP["gml_3_1_1"], "Envelope"),
            attributes={"srsName": "EPSG:4326"},
        )

        self.builder.add_foreign_child(env, etree.QName(
            NAMESPACE_LOOKUP["gml_3_1_1"], "lowerCorner"), f"{minx} {miny}")
        self.builder.add_foreign_child(env, etree.QName(
            NAMESPACE_LOOKUP["gml_3_1_1"], "upperCorner"), f"{maxx} {maxy}")

    def _build_sort(self, sort_el, sort_by):
        """
        sort_by = [
            ("dc:title", "ASC"),
            ("dc:date", "DESC"),
        ]
        """
        for prop, order in sort_by:
            sp = self.builder.add_foreign_child(
                sort_el,
                etree.QName(NAMESPACE_LOOKUP["ogc"], "SortProperty"),
            )
            self.builder.add_foreign_child(
                sp,
                etree.QName(NAMESPACE_LOOKUP["ogc"], "PropertyName"),
                text=prop,
            )
            self.builder.add_foreign_child(
                sp,
                etree.QName(NAMESPACE_LOOKUP["ogc"], "SortOrder"),
                text=order,
            )
