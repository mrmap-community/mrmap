"""Output schema negotiation of the CSW endpoint (#787, SonarCloud S5332).

``/csw`` answers records in one schema only: the ISO 19139 gmd schema. Its
identifier is normative and keeps the http scheme it was published with - it
names a schema and is never requested, see the ``NOSONAR`` annotations on the
lines that compare and advertise it. That makes the comparison itself the
behaviour worth pinning down: a client asking for any other identifier, or for
the same identifier in another spelling, has to be turned away with an OGC
exception report naming the offending parameter instead of being answered.
"""

from csw.exceptions import NotSupported
from django.test import SimpleTestCase

GET_RECORDS = {
    'SERVICE': 'CSW',
    'REQUEST': 'GetRecords',
    'VERSION': '2.0.2',
}


class CswOutputSchemaTests(SimpleTestCase):
    def test_foreign_output_schema_is_rejected_naming_the_parameter(self):
        response = self.client.get('/csw', {
            **GET_RECORDS,
            'outputSchema': 'http://purl.org/dc/elements/1.1/',
        })

        self.assertIsInstance(response, NotSupported)
        self.assertEqual(response.get_locator(), 'outputSchema')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')

    def test_the_gmd_identifier_is_compared_verbatim(self):
        # The identifier of the one supported schema is compared as it is
        # written in the specification, so a re-spelling of it - here the same
        # schema behind the https scheme - is not the supported schema and
        # must not silently be served.
        response = self.client.get('/csw', {
            **GET_RECORDS,
            'outputSchema': 'https://www.isotc211.org/2005/gmd',
        })

        self.assertIsInstance(response, NotSupported)
        self.assertEqual(response.get_locator(), 'outputSchema')

    def test_an_omitted_output_schema_defaults_to_the_supported_one(self):
        # Without the parameter the comparison falls through to the operation
        # itself, which is what proves the default of the check: reaching the
        # database is not part of this test, so the request is answered before
        # it by the missing type names check of the same method.
        response = self.client.get('/csw', {
            **GET_RECORDS,
            'typeNames': 'gmd:MD_Metadata,gmd:MD_Broken',
        })

        self.assertIsInstance(response, NotSupported)
        self.assertEqual(response.get_locator(), 'typeNames')
