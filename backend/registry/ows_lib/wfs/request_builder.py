from lxml import etree
from registry.ows_lib.xml.builder import XSDSkeletonBuilder


class WFSBuilder(XSDSkeletonBuilder):
    def __init__(self, service_version="2.0.2"):
        self.builder = XSDSkeletonBuilder(
            ("wfs", "GetCapabilitites", service_version)
        )

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
