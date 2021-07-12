import copy

from django.contrib.gis.geos import Polygon
from django.template.loader import render_to_string
from eulxml import xmlmap
from lxml import etree

from epsg_registry_offline.utils import adjust_axis_order


class Filter(xmlmap.XmlObject):
    name = xmlmap.StringField(xpath="name()")

    def get_filter_namespace(self):
        if ":" in self.name:
            return self.name.split(":")[0]
        else:
            return ""

    @classmethod
    def init_within_filter_node(cls,
                                value_reference,
                                polygon: Polygon,
                                filter_namespace: str,
                                filter_namespace_url: str,
                                gml_namespace_url: str,
                                axis_order_correction: bool = True):
        if axis_order_correction:
            polygon = adjust_axis_order(polygon)
        within_filter = render_to_string(template_name="resourceNew/xml/wfs/filter_within_v2.xml",
                                         context={"value_reference": value_reference,
                                                  "polygon": polygon,
                                                  "filter_namespace": filter_namespace,
                                                  "filter_namespace_url": filter_namespace_url,
                                                  "gml_namespace_url": gml_namespace_url})
        return etree.fromstring(within_filter)

    @classmethod
    def init_secured_filter_node(cls,
                                 value_reference,
                                 polygon: Polygon,
                                 filter_namespace: str = "ogc",
                                 filter_namespace_url: str = "http://www.opengis.net/ogc",
                                 gml_namespace_url: str = "http://www.opengis.net/gml",
                                 axis_order_correction: bool = True):

        if axis_order_correction:
            polygon = adjust_axis_order(polygon)
        filter_node = render_to_string(template_name="resourceNew/xml/wfs/filter_v2.xml",
                                       context={"value_reference": value_reference,
                                                "polygon": polygon,
                                                "filter_namespace": filter_namespace,
                                                "filter_namespace_url": filter_namespace_url,
                                                "gml_namespace_url": gml_namespace_url})
        return etree.fromstring(filter_node)

    def secure_spatial(self, value_reference, polygon: Polygon, axis_order_correction: bool = True):
        filter_namespace = self.get_filter_namespace()
        filter_namespace_url = self.context['namespaces'].get(filter_namespace)
        gml_namespace_url = self.context['namespaces'].get("gml", "http://www.opengis.net/gml")
        within_tree = self.init_within_filter_node(value_reference=value_reference,
                                                   polygon=polygon,
                                                   filter_namespace=filter_namespace,
                                                   filter_namespace_url=filter_namespace_url,
                                                   axis_order_correction=axis_order_correction,
                                                   gml_namespace_url=gml_namespace_url)

        if "And" in self.name:
            # append geometry filter as sub element
            self.node.append(within_tree)
        else:
            old_filter = copy.deepcopy(self.node)
            if filter_namespace:
                and_element = etree.Element("{" + self.context['namespaces'].get(filter_namespace) + "}And",
                                            nsmap=self.context["namespaces"])
            else:
                and_element = etree.Element("And")
            and_element.append(old_filter)
            and_element.append(within_tree)
            # add new <fes:And></fes:And> around current node
            # after that, append geometry filter as sub element
            self.node.getparent().replace(self.node, and_element)
