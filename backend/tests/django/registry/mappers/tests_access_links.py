from pathlib import Path

from django.test import SimpleTestCase
from registry.mappers.parsers.access_links import (ExtractionStatus, LinkType,
                                                   extract_access_links)

TEST_DATA = Path(__file__).parent.resolve() / "../../test_data"

GMD = 'xmlns:gmd="http://www.isotc211.org/2005/gmd"'
GCO = 'xmlns:gco="http://www.isotc211.org/2005/gco"'
SRV = 'xmlns:srv="http://www.isotc211.org/2005/srv"'
XLINK = 'xmlns:xlink="http://www.w3.org/1999/xlink"'


def distribution_xml(*resources: str) -> bytes:
    """ Wrap CI_OnlineResource bodies into a distributionInfo branch. """
    links = "".join(
        f"<gmd:onLine><gmd:CI_OnlineResource>{resource}"
        f"</gmd:CI_OnlineResource></gmd:onLine>"
        for resource in resources)
    return (
        f'<gmd:MD_Metadata {GMD} {GCO} {SRV} {XLINK}>'
        f'<gmd:distributionInfo><gmd:MD_Distribution>'
        f'<gmd:transferOptions><gmd:MD_DigitalTransferOptions>'
        f'{links}'
        f'</gmd:MD_DigitalTransferOptions></gmd:transferOptions>'
        f'</gmd:MD_Distribution></gmd:distributionInfo>'
        f'</gmd:MD_Metadata>').encode("utf-8")


def url_xml(url: str) -> str:
    return f"<gmd:linkage><gmd:URL>{url}</gmd:URL></gmd:linkage>"


class AccessLinkFixtureTest(SimpleTestCase):
    """ The checked in harvested records answer their advertised access
        information through the extractor. """

    def test_dataset_fixture_yields_capabilities_and_operation_candidates(self):
        extraction = extract_access_links(
            TEST_DATA / "iso_metadata" / "dataset.xml",
            origin_url="https://example.org/csw?getrecordbyid=RBSN_FF")

        self.assertEqual(extraction.status, ExtractionStatus.OK)
        self.assertEqual(len(extraction.records), 1)
        record = extraction.records[0]
        self.assertEqual(record.record_type, "dataset")
        self.assertEqual(record.file_identifier,
                         "de.dwd.geoserver.fach.RBSN_FF")
        self.assertEqual(record.resource_identifiers,
                         ("https://registry.gdi-de.org/id/de.bund.dwd"
                          "/de.dwd.geoserver.fach.RBSN_FF",))
        self.assertEqual(record.origin_url,
                         "https://example.org/csw?getrecordbyid=RBSN_FF")
        self.assertEqual(record.warnings, ())

        self.assertEqual(len(record.links), 2)
        capabilities, get_feature = record.links

        self.assertEqual(
            capabilities.url,
            "https://maps.dwd.de/geoserver/dwd/RBSN_FF/ows?service=wms"
            "&version=1.3.0&request=GetCapabilities")
        self.assertEqual(capabilities.link_type, LinkType.CAPABILITIES)
        self.assertEqual(capabilities.protocol,
                         "OGC:WMS-1.3.0-http-get-capabilities")
        self.assertEqual(capabilities.name,
                         "WMS Capabilities für RBSN_FF")
        self.assertEqual(capabilities.description,
                         "Liefert das WMS Capablities Dokument.")
        self.assertEqual(capabilities.function, "information")
        self.assertEqual(capabilities.request, "GetCapabilities")
        self.assertEqual(capabilities.type_names, ())

        self.assertEqual(
            get_feature.url,
            "https://maps.dwd.de/geoserver/dwd/RBSN_FF/ows?service=wfs"
            "&version=2.0.0&request=GetFeature&typeNames=RBSN_FF"
            "&outputFormat=csv&count=100&sortBy=M_DATE%20D")
        self.assertEqual(get_feature.link_type, LinkType.OGC_OPERATION)
        self.assertEqual(get_feature.service, "wfs")
        self.assertEqual(get_feature.type_names, ("RBSN_FF",))
        # the download function must not hide the operation candidate
        self.assertEqual(get_feature.function, "download")

    def test_service_fixture_yields_distinct_operation_endpoints(self):
        extraction = extract_access_links(
            TEST_DATA / "iso_metadata" / "service.xml")
        self.assertEqual(extraction.status, ExtractionStatus.OK)
        record = extraction.records[0]
        self.assertEqual(record.record_type, "service")
        # "view" is a category, not a proof of a WMS
        self.assertEqual(record.service_type, "view")
        self.assertEqual(record.service_type_version, "OGC:WMS 1.3.0")
        self.assertEqual(record.coupling_type, "tight")

        self.assertEqual(
            [operation.name for operation in record.operations],
            ["GetCapabilities", "GetFeatureInfo", "GetMap"])
        for operation in record.operations:
            self.assertEqual(operation.dcp, "WebServices")
            self.assertIsNotNone(operation.connect_point)
        connect_points = {
            operation.connect_point.url
            for operation in record.operations}
        self.assertEqual(len(connect_points), 2)
        self.assertEqual(
            record.operations[0].connect_point.link_type,
            LinkType.CAPABILITIES)

        self.assertEqual(len(record.links), 2)
        self.assertEqual(
            {link.link_type for link in record.links},
            {LinkType.CAPABILITIES, LinkType.UNKNOWN})

    def test_wms_service_metadata_fixture_retains_coupling_data(self):
        extraction = extract_access_links(
            TEST_DATA / "wms-service-metadata.xml")
        self.assertEqual(extraction.status, ExtractionStatus.OK)
        record = extraction.records[0]

        self.assertEqual(record.coupling_type, "tight")
        operates_on = [
            hint for hint in record.coupling_hints if hint.uuidref]
        self.assertEqual(len(operates_on), 1)
        self.assertEqual(
            operates_on[0].uuidref,
            "19A39B3A-2D9E-4805-A5E6-56A5CA3EC8CB")
        self.assertEqual(
            operates_on[0].href,
            "https://registry.gdi-de.org/id/de.hh"
            "/72796D51-86BC-4343-AE77-85ECAFFACF15")

        coupled = [
            hint for hint in record.coupling_hints if hint.identifier]
        self.assertEqual(
            [hint.operation_name for hint in coupled],
            ["GetCapabilities", "GetMap", "GetFeatureInfo"])
        for hint in coupled:
            self.assertEqual(
                hint.identifier,
                "https://registry.gdi-de.org/id/de.hh"
                "/72796D51-86BC-4343-AE77-85ECAFFACF15")

        # metadata identity and resource identity stay distinct
        self.assertNotIn(record.file_identifier, {
            hint.identifier for hint in record.coupling_hints})
        self.assertNotIn(record.file_identifier, {
            hint.href for hint in record.coupling_hints})


class AccessLinkExtractionTest(SimpleTestCase):
    """ Structural behavior of the extractor over crafted records. """

    def test_repeated_links_are_kept_with_their_xml_location(self):
        xml = distribution_xml(
            url_xml("https://a.example/cap?request=GetCapabilities"),
            url_xml("https://a.example/cap?request=GetCapabilities"),
        )
        record = extract_access_links(xml).records[0]
        self.assertEqual(len(record.links), 2)
        self.assertNotEqual(record.links[0].source, record.links[1].source)
        self.assertTrue(record.links[1].source.endswith(
            "gmd:onLine[2]/gmd:CI_OnlineResource"))

    def test_distributor_transfer_options_are_extracted(self):
        xml = (
            f'<gmd:MD_Metadata {GMD} {GCO} {SRV} {XLINK}>'
            f'<gmd:distributionInfo><gmd:MD_Distribution>'
            f'<gmd:distributor><gmd:MD_Distributor>'
            f'<gmd:distributorTransferOptions>'
            f'<gmd:MD_DigitalTransferOptions>'
            f'<gmd:onLine><gmd:CI_OnlineResource>'
            f'{url_xml("https://dist.example/data.csv")}'
            f'<gmd:function><gmd:CI_OnLineFunctionCode '
            f'codeList="https://example/codelist#CI_OnLineFunctionCode" '
            f'codeListValue="download"/></gmd:function>'
            f'</gmd:CI_OnlineResource></gmd:onLine>'
            f'</gmd:MD_DigitalTransferOptions>'
            f'</gmd:distributorTransferOptions>'
            f'</gmd:MD_Distributor></gmd:distributor>'
            f'</gmd:MD_Distribution></gmd:distributionInfo>'
            f'</gmd:MD_Metadata>').encode("utf-8")
        record = extract_access_links(xml).records[0]
        self.assertEqual(len(record.links), 1)
        self.assertEqual(record.links[0].link_type, LinkType.DOWNLOAD)
        self.assertEqual(record.links[0].function, "download")

    def test_optional_fields_may_be_absent(self):
        xml = distribution_xml(url_xml("https://only-url.example/metadata"))
        record = extract_access_links(xml).records[0]
        self.assertEqual(len(record.links), 1)
        link = record.links[0]
        self.assertIsNone(link.protocol)
        self.assertIsNone(link.application_profile)
        self.assertIsNone(link.name)
        self.assertIsNone(link.description)
        self.assertIsNone(link.function)
        self.assertEqual(link.link_type, LinkType.UNKNOWN)

    def test_empty_urls_are_skipped_without_rejecting_the_record(self):
        xml = distribution_xml(
            "<gmd:linkage><gmd:URL>  </gmd:URL></gmd:linkage>",
            "<gmd:linkage><gmd:URL/></gmd:linkage>",
            url_xml("https://valid.example/srv?request=GetCapabilities"),
        )
        extraction = extract_access_links(xml)
        self.assertEqual(extraction.status, ExtractionStatus.OK)
        record = extraction.records[0]
        self.assertEqual(len(record.links), 1)
        self.assertEqual(record.links[0].link_type, LinkType.CAPABILITIES)
        self.assertEqual(len(record.warnings), 2)
        for warning in record.warnings:
            self.assertIn("without URL", warning)

    def test_namespace_uris_are_matched_not_prefix_spellings(self):
        xml = (
            '<md:MD_Metadata'
            ' xmlns:md="http://www.isotc211.org/2005/gmd"'
            ' xmlns:gc="http://www.isotc211.org/2005/gco">'
            '<md:distributionInfo><md:MD_Distribution>'
            '<md:transferOptions><md:MD_DigitalTransferOptions>'
            '<md:onLine><md:CI_OnlineResource>'
            '<md:linkage><md:URL>https://prefix.example'
            '?request=GetCapabilities</md:URL></md:linkage>'
            '<md:protocol><gc:CharacterString>'
            'OGC:WMS-1.3.0-http-get-capabilities'
            '</gc:CharacterString></md:protocol>'
            '</md:CI_OnlineResource></md:onLine>'
            '</md:MD_DigitalTransferOptions></md:transferOptions>'
            '</md:MD_Distribution></md:distributionInfo>'
            '</md:MD_Metadata>').encode("utf-8")
        record = extract_access_links(xml).records[0]
        self.assertEqual(len(record.links), 1)
        self.assertEqual(record.links[0].link_type, LinkType.CAPABILITIES)

    def test_contact_homepages_are_not_access_links(self):
        xml = (
            f'<gmd:MD_Metadata {GMD} {GCO} {SRV} {XLINK}>'
            f'<gmd:contact><gmd:CI_ResponsibleParty>'
            f'<gmd:contactInfo><gmd:CI_Contact>'
            f'<gmd:onlineResource><gmd:CI_OnlineResource>'
            f'{url_xml("https://homepage.example/contact")}'
            f'</gmd:CI_OnlineResource></gmd:onlineResource>'
            f'</gmd:CI_Contact></gmd:contactInfo>'
            f'</gmd:CI_ResponsibleParty></gmd:contact>'
            f'</gmd:MD_Metadata>').encode("utf-8")
        record = extract_access_links(xml).records[0]
        self.assertEqual(record.links, ())
        self.assertEqual(record.warnings, ())

    def test_information_links_are_metadata_references_not_services(self):
        xml = distribution_xml(
            url_xml("https://info.example/landing-page")
            + '<gmd:function><gmd:CI_OnLineFunctionCode '
              'codeListValue="information"/></gmd:function>',
        )
        record = extract_access_links(xml).records[0]
        self.assertEqual(record.links[0].link_type,
                         LinkType.METADATA_REFERENCE)

    def test_external_entities_are_not_resolved(self):
        xml = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE m [<!ENTITY secret SYSTEM "file:///etc/passwd">]>'
            b'<gmd:MD_Metadata '
            b'xmlns:gmd="http://www.isotc211.org/2005/gmd">'
            b'<gmd:distributionInfo><gmd:MD_Distribution>'
            b'<gmd:transferOptions><gmd:MD_DigitalTransferOptions>'
            b'<gmd:onLine><gmd:CI_OnlineResource>'
            b'<gmd:linkage><gmd:URL>&secret;</gmd:URL></gmd:linkage>'
            b'</gmd:CI_OnlineResource></gmd:onLine>'
            b'</gmd:MD_DigitalTransferOptions></gmd:transferOptions>'
            b'</gmd:MD_Distribution></gmd:distributionInfo>'
            b'</gmd:MD_Metadata>')
        record = extract_access_links(xml).records[0]
        # the entity was neither expanded nor fetched from the filesystem
        self.assertEqual(record.links, ())
        self.assertEqual(len(record.warnings), 1)


class AccessLinkStatusTest(SimpleTestCase):
    """ Failure states of the stored xml are answered explicitly. """

    def test_missing_content(self):
        extraction = extract_access_links(b"")
        self.assertEqual(extraction.status, ExtractionStatus.MISSING)
        self.assertTrue(extraction.detail)
        self.assertEqual(extraction.records, ())

    def test_unreadable_input(self):
        extraction = extract_access_links(None)
        self.assertEqual(extraction.status, ExtractionStatus.UNREADABLE)
        self.assertTrue(extraction.detail)

    def test_malformed_xml(self):
        extraction = extract_access_links(
            b'<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd">'
            b'<unclosed>')
        self.assertEqual(extraction.status, ExtractionStatus.MALFORMED)
        self.assertTrue(extraction.detail)

    def test_document_without_metadata_records(self):
        extraction = extract_access_links(b'<csw:GetRecordsResponse '
                                          b'xmlns:csw="http://www.opengis'
                                          b'.net/cat/csw/2.0.2"/>')
        self.assertEqual(extraction.status, ExtractionStatus.NO_RECORDS)
        self.assertEqual(extraction.records, ())
