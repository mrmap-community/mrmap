"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 26.05.20

"""
from copy import copy

from django.test import TestCase, Client
from django.urls import reverse

from MrMap.settings import GENERIC_NAMESPACE_TEMPLATE
from service.helper import xml_helper
from service.models import Service
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD
from tests.utils import activate_service

CSW_PATH = "csw:get-csw-results"
WRONG_STATUS_CODE_TEMPLATE = "CSW GetRecords returned with code {}"
INVALID_XML_MSG = "Response contains invalid XML!"


class CswViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.groups.first(), how_much_services=10)

        # Make sure services are activated
        services = Service.objects.all()
        for service in services:
            activate_service(service, True)

        self.test_id = services.first().metadata.identifier

    def test_get_records(self):
        """ Test whether the GetRecords operation runs properly

        Returns:

        """
        get_records_param = {
            "service": "CSW",
            "version": "2.0.2",
            "request": "GetRecords",
            "elementsetname": "brief",
            "resulttype": "results",
        }
        response = self.client.get(
            reverse(CSW_PATH),
            data=get_records_param
        )
        status_code = response.status_code
        content = response.content
        content_xml = xml_helper.parse_xml(content)

        self.assertEqual(response.status_code, 200, WRONG_STATUS_CODE_TEMPLATE.format(status_code))
        self.assertIsNotNone(content_xml, INVALID_XML_MSG)

    def test_get_records_sort(self):
        """ Test whether the sorting parameter is working properly

        Returns:

        """
        get_records_param = {
            "service": "CSW",
            "version": "2.0.2",
            "request": "GetRecords",
            "elementsetname": "brief",
            "resulttype": "results",
            "sortby": "dc:title:D",
        }

        response = self.client.get(
            reverse(CSW_PATH),
            data=get_records_param
        )
        status_code = response.status_code
        content = response.content
        content_xml = xml_helper.parse_xml(content)

        self.assertEqual(response.status_code, 200, WRONG_STATUS_CODE_TEMPLATE.format(status_code))
        self.assertIsNotNone(content_xml, INVALID_XML_MSG)

        # Iterate over dc:title objects and check whether they are sorted correctly!
        title_elems = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("title"), content_xml)
        titles = [xml_helper.try_get_text_from_xml_element(title_elem) for title_elem in title_elems]
        titles_sorted = copy(titles)
        titles.sort(reverse=True)  # Check the descending sorted way
        self.assertEqual(titles, titles_sorted)

    def test_get_records_constraint(self):
        """ Test whether the constraint parameter is working properly

        Returns:

        """
        get_records_param = {
            "service": "CSW",
            "version": "2.0.2",
            "request": "GetRecords",
            "elementsetname": "brief",
            "resulttype": "results",
            "constraint": "dc:identifier like %{}%".format(self.test_id),
            "constraintlanguage": "CQL_TEXT",
        }

        response = self.client.get(
            reverse(CSW_PATH),
            data=get_records_param
        )
        status_code = response.status_code
        content = response.content
        content_xml = xml_helper.parse_xml(content)

        self.assertEqual(response.status_code, 200, WRONG_STATUS_CODE_TEMPLATE.format(status_code))
        self.assertIsNotNone(content_xml, INVALID_XML_MSG)

        # Iterate over dc:title objects and check whether they are sorted correctly!
        identifier_elems = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("identifier"), content_xml)
        identifier = [xml_helper.try_get_text_from_xml_element(id_elem) for id_elem in identifier_elems]
        identifier_inside = [self.test_id in id_elem for id_elem in identifier]
        self.assertTrue(False not in identifier_inside, "A result was returned, which does not fit to the given constraint parameter!")

    def test_get_records_by_id(self):
        """ Test for checking if the GetRecordsById is working fine or not.

        Returns:

        """
        get_records_param = {
            "service": "CSW",
            "version": "2.0.2",
            "request": "GetRecordById",
            "id": self.test_id,
            "elementsetname": "full",
        }

        response = self.client.get(
            reverse(CSW_PATH),
            data=get_records_param
        )
        status_code = response.status_code
        content = response.content
        content_xml = xml_helper.parse_xml(content)

        self.assertEqual(response.status_code, 200, WRONG_STATUS_CODE_TEMPLATE.format(status_code))
        self.assertIsNotNone(content_xml, INVALID_XML_MSG)

        # Check that the results are correct in amount and quality
        num_returned_elems = int(xml_helper.try_get_attribute_from_xml_element(xml_elem=content_xml, attribute="numberOfRecordsMatched", elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("SearchResults")))
        self.assertEqual(num_returned_elems, 1, "More than one element returned on GetRecordsById with only one used identifier!")
        real_returned_elems = xml_helper.try_get_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("Record"), content_xml)
        num_real_returned_elems = len(real_returned_elems)
        self.assertEqual(num_real_returned_elems, num_returned_elems, "csw:SearchResults contains wrong numberOfRecordsMatched! {} stated but {} returned!".format(num_returned_elems, num_real_returned_elems))

        identifiers = [xml_helper.try_get_text_from_xml_element(real_returned_elem, "//" + GENERIC_NAMESPACE_TEMPLATE.format("identifier")) for real_returned_elem in real_returned_elems]
        identifiers_identical = [identifier == self.test_id for identifier in identifiers]
        self.assertTrue(False not in identifiers_identical, "Elements with not matching identifier has been returned: {}".format(", ".join(identifiers)))

    def test_get_records_md_metadata(self):
        """ Test for checking if the GetRecordsById is working fine or not.

        Returns:

        """
        get_records_param = {
            "service": "CSW",
            "version": "2.0.2",
            "request": "GetRecordsById",
            "id": self.test_id,
            "elementsetname": "brief",
            "typenames": "gmd:MD_Metadata",
            "outputschema": "http://www.isotc211.org/2005/gmd",
        }

        response = self.client.get(
            reverse(CSW_PATH),
            data=get_records_param
        )
        status_code = response.status_code
        content = response.content
        content_xml = xml_helper.parse_xml(content)

        self.assertEqual(response.status_code, 200, WRONG_STATUS_CODE_TEMPLATE.format(status_code))
        self.assertIsNotNone(content_xml, INVALID_XML_MSG)

    def test_exception_report(self):
        """ Test for checking if the ows:ExceptionReport is working fine or not.

        Test by requesting a wrong operation

        Returns:

        """
        get_records_param = {
            "service": "CSW",
            "version": "2.0.2",
            "request": "WRONG_OPERATION",
            "id": self.test_id,
            "elementsetname": "brief",
            "typenames": "gmd:MD_Metadata",
            "outputschema": "http://www.isotc211.org/2005/gmd",
        }

        response = self.client.get(
            reverse(CSW_PATH),
            data=get_records_param
        )
        status_code = response.status_code
        content = response.content
        content_xml = xml_helper.parse_xml(content)

        self.assertEqual(response.status_code, 200, WRONG_STATUS_CODE_TEMPLATE.format(status_code))
        self.assertIsNotNone(content_xml, INVALID_XML_MSG)
        exception_report_elem = xml_helper.try_get_single_element_from_xml("//" + GENERIC_NAMESPACE_TEMPLATE.format("ExceptionReport"), content_xml)
        self.assertIsNotNone(exception_report_elem, "No ows:ExceptionReport was generated!")
