"""Transport policy of the seeded defaults (#782, SonarCloud S5332).

``load_categories`` fetches the category URLs over the network and the licence
links are rendered to users, so every seeded URL must use https. The single
exception lives inside the eionet template: the INSPIRE theme URI there is a
normative identifier passed as a query parameter and keeps its http scheme -
the check below only ever sees the eionet endpoint itself.
"""

from django.test import SimpleTestCase

from MrMap.management.commands.setup_settings import CATEGORIES, LICENCES

CSW202_SCHEMA = ('CSW', '2.0.2')
WMS111_SCHEMA = ('WMS', '1.1.1')


class SeededTransportPolicyTests(SimpleTestCase):
    def test_category_fetch_urls_are_https(self):
        for origin, url in CATEGORIES.items():
            self.assertTrue(url.startswith('https://'), origin)

    def test_license_urls_are_https(self):
        for licence in LICENCES:
            for field in ('symbol_url', 'description_url'):
                value = licence[field]
                if value is not None:
                    self.assertTrue(value.startswith('https://'), (licence['identifier'], field))

    def test_mapper_schema_location_hints_are_https(self):
        # The hint is documentation only - the mapper never fetches it - but
        # where the registry speaks of a schema, it should name the https
        # location; wms130 set that precedent.
        from registry.mappers.configs import csw202, wms111
        self.assertTrue(csw202.XPATH_MAP[CSW202_SCHEMA]['_schema'].startswith('https://'))
        self.assertTrue(wms111.XPATH_MAP[WMS111_SCHEMA]['_schema'].startswith('https://'))
