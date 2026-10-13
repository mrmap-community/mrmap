from django.test import TestCase
from registry.mappers.configs import XPATH_MAP
from registry.mappers.persistence.handler import PersistenceHandler
from registry.mappers.xml_mapper import XmlMapper
from registry.models.metadata import Keyword


class KeywordMappingTest(TestCase):
    def keyword_specs(self, mapping):
        for value in mapping.values():
            if isinstance(value, dict):
                if value.get('_model') == 'registry.Keyword':
                    yield value
                yield from self.keyword_specs(value)

    def test_all_keyword_mappings_skip_blanks_before_persistence(self):
        xml = '<root><Keyword/><Keyword> </Keyword><Keyword>\t\n</Keyword><Keyword>  valid  </Keyword></root>'
        for resource, mapping in XPATH_MAP.items():
            if resource[0] == 'DescribeFeatureType':
                continue
            specs = list(self.keyword_specs(mapping))
            self.assertTrue(specs, resource)
            for spec in specs:
                with self.subTest(resource=resource, xpath=spec['_base_xpath']):
                    spec = spec | {'_base_xpath': './Keyword'}
                    mapper = XmlMapper(xml, {'keywords': spec})
                    parsed = mapper.traverse_spec(spec, is_many=True)
                    self.assertEqual([item.keyword for item in parsed], ['  valid  '])
                    self.assertEqual(len(mapper.read_all_from_cache()), 1)
                    PersistenceHandler(mapper).persist_all()
                    self.assertEqual(list(Keyword.objects.values_list('keyword', flat=True)), ['  valid  '])

    def test_all_blank_keyword_list_can_be_persisted(self):
        spec = next(self.keyword_specs(next(iter(XPATH_MAP.values()))))
        spec = spec | {'_base_xpath': './Keyword'}
        mapper = XmlMapper('<root><Keyword/><Keyword> </Keyword></root>', {'keywords': spec})
        self.assertEqual(mapper.traverse_spec(spec, is_many=True), [])
        self.assertEqual(PersistenceHandler(mapper).persist_all(), {})
        self.assertFalse(Keyword.objects.exists())
