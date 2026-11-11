"""Empty-but-present KVP parameters survive the request analysis (#1154).

Every standard WMS client sends ``STYLES=`` -- empty as OGC 05-008, 7.2.2
prescribes for the default style -- and a GetMap through the mrmap-proxy lost
exactly that parameter: the request analysis kept a whitelisted key only ``if
value:``, so upstream never read ``STYLES`` at all and refused with
``missing parameters ['styles']`` served to the caller as a 500. The same loss
class applies to any whitelisted parameter a client may legitimately send
empty; the proxy has to forward the caller's KVP verbatim, an empty value
included.

Pinned here: the parameter dict keeps a present-but-empty value and still
invents nothing for an absent one, the url rebuild writes the empty parameter
back empty (and keeps a blank of the url it is given), the proxy path carries
``STYLES=`` into the upstream request it sends, and the request documents
synthesized from the same dict -- which carry values, not emptiness -- stay
what they were for a request which did not name the parameter.
"""
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qsl, urlparse

from django.test import SimpleTestCase
from lxml import etree
from registry.ows_lib.request.ogc_request import OGCRequest
from registry.ows_lib.request.utils import update_queryparams
from registry.proxy.mixins import OgcServiceProxyView

GET_MAP = {
    'SERVICE': 'WMS',
    'VERSION': '1.3.0',
    'REQUEST': 'GetMap',
    'LAYERS': 'OSM-WMS',
    'STYLES': '',
    'CRS': 'EPSG:3857',
    'BBOX': '600000,5700000,610000,5710000',
    'WIDTH': '300',
    'HEIGHT': '300',
    'FORMAT': 'image/png',
}


def serialize(element) -> bytes:
    """The document of an element, for a comparison which sees every child."""
    return etree.tostring(element)


class OgcQueryParamsTest(SimpleTestCase):
    """the parameter dict the proxy rebuilds its upstream request from"""

    def test_a_present_empty_parameter_stays_with_its_empty_value(self):
        # the repro of the issue: a standard client's GetMap carries STYLES=
        # and the analysis must hand it on rather than drop the key
        ogc_request = OGCRequest(method='GET', params=dict(GET_MAP))

        self.assertIn('STYLES', ogc_request.ogc_query_params)
        self.assertEqual('', ogc_request.ogc_query_params['STYLES'])
        # the class of the loss, not only its most fatal member: TIME is as
        # legal empty as STYLES (OGC 05-008, 7.2.3.8)
        empty_time = OGCRequest(method='GET', params={**GET_MAP, 'TIME': ''})
        self.assertEqual('', empty_time.ogc_query_params['TIME'])

    def test_an_empty_value_keeps_the_canonical_spelling(self):
        # the whitelist answers the parameter under its canonical spelling
        # whatever case the caller chose -- an empty value changes nothing
        # about that, the issue's STYLES= arrives as styles= just as well
        ogc_request = OGCRequest(
            method='GET', params={'service': 'WMS', 'styles': ''})

        self.assertEqual('', ogc_request.ogc_query_params['STYLES'])

    def test_a_parameter_the_request_does_not_name_stays_absent(self):
        # keeping an empty value must not invent values: a parameter the
        # request never sent is absent, not empty
        ogc_request = OGCRequest(method='GET', params=dict(GET_MAP))

        self.assertNotIn('TIME', ogc_request.ogc_query_params)
        self.assertNotIn('EXCEPTIONS', ogc_request.ogc_query_params)


class UpdateQueryParamsTest(SimpleTestCase):
    """the rebuild of a url from query parameters"""

    def test_the_empty_parameter_is_written_back_empty(self):
        url = update_queryparams(
            url='https://up.example/wms?', params=dict(GET_MAP))

        pairs = parse_qsl(urlparse(url).query, keep_blank_values=True)
        self.assertIn(('STYLES', ''), pairs)
        # the value is empty rather than absent: parse_qsl without
        # keep_blank_values does not see the parameter at all
        self.assertNotIn(
            'STYLES', [name for name, _ in parse_qsl(urlparse(url).query)])

    def test_a_blank_of_the_url_is_not_dropped_by_the_rebuild(self):
        # the same loss class on the other side of the rebuild: an empty
        # parameter already in the url survives updating the other ones
        url = update_queryparams(
            url='https://up.example/wms?token=&a=1',
            params={'BBOX': '1,2,3,4'})

        pairs = parse_qsl(urlparse(url).query, keep_blank_values=True)
        self.assertIn(('token', ''), pairs)
        self.assertIn(('a', '1'), pairs)
        self.assertIn(('BBOX', '1,2,3,4'), pairs)


class ProxyForwardsEmptyParamsTest(SimpleTestCase):
    """the upstream request the proxy rebuilds from the caller's parameters"""

    def test_the_get_map_rebuild_carries_the_empty_stYLES(self):
        view = OgcServiceProxyView()
        view.service = SimpleNamespace(
            operation_urls=SimpleNamespace(values=lambda *args: SimpleNamespace(
                get=lambda **kwargs: {'id': 1, 'url': 'https://up.example/wms?'})))
        view.ogc_request = OGCRequest(method='GET', params=dict(GET_MAP))
        with patch.object(
                OgcServiceProxyView, 'remote_service',
                new=SimpleNamespace(send_request=lambda request: request)):
            remote_request = view.get_remote_response()

        pairs = parse_qsl(
            urlparse(remote_request.url).query, keep_blank_values=True)
        self.assertIn(('STYLES', ''), pairs)
        self.assertNotIn(
            'STYLES', [name for name, _ in parse_qsl(
                urlparse(remote_request.url).query)])


class SynthesizedDocumentsTest(SimpleTestCase):
    """the KVP-to-XML documents which read the same parameter dict

    A request document carries values, not emptiness: an empty parameter is
    answered here as the absent one was before the dict learned to keep it, so
    the empty value reaches upstream but never a synthesized document."""

    def test_an_empty_paging_pages_nothing_in_the_get_feature(self):
        # int('') raises -- COUNT is whitelisted, so an empty COUNT now
        # reaches the read; it pages nothing, as it did while the whitelist
        # dropped the empty value. (KVP startIndex never reaches this
        # synthesis -- it is not whitelisted -- the 'or 0' read only keeps it
        # safe if that ever changes.) The KVP GetFeature builder assigns the
        # document to _xml_request itself while the property rebinds that
        # name to the builder's missing return, so the built element is read
        # where the builder left it.
        named = OGCRequest(method='GET', params={
            'SERVICE': 'WFS', 'VERSION': '2.0.0', 'REQUEST': 'GetFeature',
            'TYPENAMES': 'ns:Roads', 'COUNT': '10'})
        empty = OGCRequest(method='GET', params={
            'SERVICE': 'WFS', 'VERSION': '2.0.0', 'REQUEST': 'GetFeature',
            'TYPENAMES': 'ns:Roads', 'COUNT': ''})
        absent = OGCRequest(method='GET', params={
            'SERVICE': 'WFS', 'VERSION': '2.0.0', 'REQUEST': 'GetFeature',
            'TYPENAMES': 'ns:Roads'})

        for request in (named, empty, absent):
            request.build_get_feature_from_get()

        self.assertEqual('10', named._xml_request.get('count'))
        self.assertEqual(
            serialize(absent._xml_request), serialize(empty._xml_request))

    def test_empty_values_stay_out_of_the_get_records_document(self):
        named = OGCRequest(method='GET', params={
            'SERVICE': 'CSW', 'VERSION': '2.0.2', 'REQUEST': 'GetRecords',
            'maxRecords': '10', 'startPosition': '3',
            'ElementSetName': 'brief'})
        empty = OGCRequest(method='GET', params={
            'SERVICE': 'CSW', 'VERSION': '2.0.2', 'REQUEST': 'GetRecords',
            'maxRecords': '', 'startPosition': '', 'resultType': '',
            'ElementSetName': ''})
        absent = OGCRequest(method='GET', params={
            'SERVICE': 'CSW', 'VERSION': '2.0.2', 'REQUEST': 'GetRecords'})

        self.assertEqual(
            '10', named.xml_request.get('maxRecords'))
        self.assertEqual(
            serialize(absent.xml_request), serialize(empty.xml_request))
        for element in (named.xml_request, empty.xml_request,
                        absent.xml_request):
            for name, value in element.attrib.items():
                self.assertNotEqual(
                    '', value,
                    f'attribute {name} is present with an empty value')
