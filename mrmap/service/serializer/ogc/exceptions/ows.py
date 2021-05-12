from MrMap.settings import XML_NAMESPACES
from lxml.etree import Element
from service.helper import xml_helper


class OWSException:
    def __init__(self, exception: Exception):
        self.exception = exception
        try:
            self.text = exception.args[0]
        except IndexError:
            self.text = "None"
        try:
            self.locator = exception.args[1]
        except IndexError:
            self.locator = "None"

        self.namespace_map = {
            None: XML_NAMESPACES["ows"],
            "xsi": XML_NAMESPACES["xsi"],
        }

        self.xsi_ns = "{" + self.namespace_map["xsi"] + "}"
        self.ows_ns = "{" + self.namespace_map[None] + "}"

    def get_exception_report(self):
        """ Creates an OWSExceptionReport from a given Exception object

        Returns:
             report (str): The exception report as string
        """
        root = Element(
            "{}ExceptionReport".format(self.ows_ns),
            nsmap=self.namespace_map,
            attrib={
                "{}schemaLocation".format(self.xsi_ns): "http://schemas.opengis.net/ows/1.1.0/owsExceptionReport.xsd",
                "version": "1.2.0",
            }
        )
        exception_elem = xml_helper.create_subelement(
            root,
            "{}Exception".format(self.ows_ns),
            attrib={
                "exceptionCode": self.exception.__class__.__name__,
                "locator": self.locator,
            }
        )
        text_elem = xml_helper.create_subelement(
            exception_elem,
            "{}ExceptionText".format(self.ows_ns)
        )
        text_elem.text = self.text

        return xml_helper.xml_to_string(root, pretty_print=True)