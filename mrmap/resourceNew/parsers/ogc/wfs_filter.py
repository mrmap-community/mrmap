import copy

from django.contrib.gis.geos import Polygon
from django.template import Template, Context
from django.template.loader import render_to_string
from eulxml import xmlmap
from lxml import etree

from epsg_registry_offline.utils import adjust_axis_order


class Filter(xmlmap.XmlObject):
    name = xmlmap.StringField(xpath="name()")


class GetFeature(xmlmap.XmlObject):
    filter = xmlmap.NodeField(xpath="wfs:Query/fes:Filter/*",
                              node_class=Filter)
    type_names = xmlmap.StringField(xpath="wfs:Query/@typeNames")

    def secure_spatial(self, value_reference, polygon: Polygon):
        polygon = adjust_axis_order(polygon)
        within_filter = render_to_string(template_name="resourceNew/xml/wfs/filter_within_v2.xml",
                                         context={"value_reference": value_reference,
                                                  "polygon": polygon,})
        within_tree = etree.fromstring(within_filter)

        if "And" in self.filter.name:
            # append geometry filter as sub element
            self.filter.node.append(within_tree)
        else:
            old_filter = copy.deepcopy(self.filter.node)
            and_element = etree.Element("{" + self.context['namespaces'].get('fes') + "}And", nsmap=self.context["namespaces"])
            and_element.append(old_filter)
            and_element.append(within_tree)
            # add new <fes:And></fes:And> around current node
            # after that, append geometry filter as sub element
            self.filter.node.getparent().replace(self.filter.node, and_element)
