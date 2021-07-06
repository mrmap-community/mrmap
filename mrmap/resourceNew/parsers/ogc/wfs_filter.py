import copy

from django.contrib.gis.geos import Polygon
from django.template import Template, Context
from django.template.loader import render_to_string
from eulxml import xmlmap
from lxml import etree


class Filter(xmlmap.XmlObject):
    name = xmlmap.StringField(xpath="name()")


class GetFeature(xmlmap.XmlObject):
    filter = xmlmap.NodeField(xpath="wfs:Query/fes:Filter/*",
                              node_class=Filter)
    type_names = xmlmap.StringField(xpath="@typeNames")

    def secure_spatial(self, value_reference, srid, coords):
        within_template_string = """
        <fes:Within xmlns:fes="http://www.opengis.net/fes/2.0"
                    xmlns:gml="http://www.opengis.net/gml/3.2">
            <fes:ValueReference>{{value_reference}}</fes:ValueReference>
            <gml:Polygon srsName="urn:x-ogc:def:crs:EPSG:{{srid}}">
                <gml:exterior>
                    <gml:LinearRing>
                        <gml:posList>{{coords}}</gml:posList>
                    </gml:LinearRing>
                </gml:exterior>
            </gml:Polygon>
        </fes:Within>
        """
        context = Context({"value_reference": value_reference,
                           "srid": srid,
                           "coords": coords})
        within_filter = Template(template_string=within_template_string).render(context=context)
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
