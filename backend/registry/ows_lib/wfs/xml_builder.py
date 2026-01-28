from django.contrib.gis.gdal.geometries import OGRGeometry
from lxml import etree
from registry.ows_lib.xml.builder import XSDSkeletonBuilder
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP


class WFSBuilder(XSDSkeletonBuilder):
    FES_NS = NAMESPACE_LOOKUP["fes_2_0"]
    GML_NS = NAMESPACE_LOOKUP["gml_3_2_2"]

    def __init__(self, service_version="2.0.2"):
        super().__init__(("wfs", "GetCapabilitites", service_version))

    def build_get_feature(
        self,
        type_names: list[str],
        *,
        filter_xml: etree._Element | None = None,
        srs_name: str | None = None,
        count: int | None = None,
        start_index: int | None = None,
    ) -> etree._Element:
        """
        Build a WFS 2.0 GetFeature request.

        :param type_names: list of feature type QNames (e.g. ["ns:Roads"])
        :param filter_xml: optional FES Filter element (already-built XML)
        :param srs_name: optional srsName
        :param count: optional max features
        :param start_index: optional start index
        """

        # ---- Root GetFeature element ----
        root = self.build_element(
            "GetFeature",
            attributes={
                "service": "WFS",
                "version": self.version,
            },
        )

        if count is not None:
            root.set("count", str(count))
        if start_index is not None:
            root.set("startIndex", str(start_index))

        # ---- Query elements ----
        for type_name in type_names:
            query = self.add_child_element(
                root,
                "Query",
                attributes={
                    "typeNames": type_name,
                    **({"srsName": srs_name} if srs_name else {}),
                },
            )

            # ---- Optional Filter (foreign namespace) ----
            if filter_xml is not None:
                query.append(filter_xml)

        return root

    def set_bbox(
        self,
        geometry: OGRGeometry,
        feature_type: etree._Element
    ) -> etree._Element:

        min_x = str(geometry.extent[0])
        min_y = str(geometry.extent[1])
        max_x = str(geometry.extent[2])
        max_y = str(geometry.extent[3])

        lower_corner = f"{min_x} f{min_y}"
        upper_corner = f"{max_x} f{max_y}"
        bbox = self.add_foreign_child(
            feature_type,
            etree.QName(NAMESPACE_LOOKUP["ows_1_1"], "WGS84BoundingBox"),
        )
        self.add_foreign_child(
            bbox,
            etree.QName(NAMESPACE_LOOKUP["ows_1_1"], "LowerCorner"),
            text=lower_corner
        )
        self.add_foreign_child(
            bbox,
            etree.QName(NAMESPACE_LOOKUP["ows_1_1"], "UpperCorner"),
            text=upper_corner
        )

        return bbox

    def build_spatial_filter(
        self,
        *,
        geometry: OGRGeometry,
        value_reference: str,
        operator: str = "Intersects",
    ) -> etree._Element:
        """
        Build a FES 2.0 spatial filter using XSDSkeletonBuilder helpers.
        """

        # <fes:Filter>
        filter_el = self.add_foreign_child(
            parent=None,  # temporary root
            qname=etree.QName(self.FES_NS, "Filter"),
        )

        # <fes:Intersects>
        intersects = self.add_foreign_child(
            filter_el,
            etree.QName(self.FES_NS, operator),
        )

        # <fes:ValueReference>
        self.add_foreign_child(
            intersects,
            etree.QName(self.FES_NS, "ValueReference"),
            text=value_reference,
        )

        # geometry → GML (foreign, but allowed)
        gml_str = geometry.gml
        # inject namespace on the root element
        if gml_str.startswith("<gml:"):
            parts = gml_str.split(" ", 1)  # after <gml:Polygon
            gml_str = f'{parts[0]} xmlns:gml="{self.GML_NS}" {parts[1]}'
        gml_el = etree.fromstring(gml_str.encode("utf-8"))
        intersects.append(gml_el)

        return filter_el

    def and_filter(
        self,
        existing_filter: etree._Element,
        new_filter: etree._Element,
    ) -> None:
        """
        AND an existing <fes:Filter> with another one.
        """

        fes_ns = self.FES_NS

        existing_children = list(existing_filter)
        new_children = list(new_filter)

        existing_filter.clear()

        and_el = self.add_foreign_child(
            existing_filter,
            etree.QName(fes_ns, "And"),
        )

        for el in existing_children:
            and_el.append(el)

        for el in new_children:
            and_el.append(el)
