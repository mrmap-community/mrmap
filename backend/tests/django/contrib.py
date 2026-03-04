from django.test import TestCase
from lxml import etree


class XpathTestCase(TestCase):

    def _get_by_xpath(self, tree, xpath: str):
        # Accept either ElementTree or Element
        if isinstance(tree, etree._ElementTree):
            root = tree.getroot()
        else:
            root = tree

        namespaces = root.nsmap.copy()
        if None in namespaces:
            namespaces["d"] = namespaces.pop(None)

        return root.xpath(xpath, namespaces=namespaces)

    def assertXpathValue(self, tree, xpath: str, expected: str, strip_result: bool = False) -> str:
        result = self._get_by_xpath(tree, xpath)
        result = result[0] if result else None
        if strip_result:
            result = result.strip()
        self.assertTrue(result == expected,
                        msg=f"Value Missmatch from xpath {xpath}: '{result}' does not equals '{expected}' ")

    def assertXpathValues(self, tree, xpath: str, expected: str) -> str:
        result = self._get_by_xpath(tree, xpath)
        self.assertListEqual([value.text for value in result], expected)

    def assertXpathCount(self, tree, xpath: str, expected_count: int) -> str:
        result = self._get_by_xpath(tree, xpath)
        self.assertEqual(len(result), expected_count)
