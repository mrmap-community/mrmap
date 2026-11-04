"""The extraction API of issue #981: mapped values without PersistenceHandler.

`XmlMapper.mapped_values()` is the read side of the mapper's single forward
traversal - persistence consumes the very same parsed instances - and
`MDMetadataXmlMapper.extract_mapped_values()` is the thin facade over it for
ISO 19139 documents. This module is the contract of both:

* shape: one record description per MD_Metadata node, values keyed by the
  mapping's field names, multiple values as lists in document order,
* the epic #669 access and coupling elements are answered from the fixtures
  the epic cites: the WMS GetCapabilities and WFS GetFeature links of
  `dataset.xml`, the operation connectPoints of `service.xml`, the operatesOn
  uuidref/href and SV_CoupledResource evidence of
  `wms-service-metadata.xml`,
* absence: an element the document does not carry answers None inside its
  dict, a whole value spec the document does not carry answers an empty list -
  and mapping stays side-effect free: no database query, no network request,
  no entry in the process-global cache,
* malformed input fails exactly like the mapper fails today - extraction is
  not allowed to be more fragile and not allowed to invent tolerance the
  harvesting path does not have,
* both consumers agree: the values of a mapped record are the values the
  persistence path writes for the same document.
"""

from pathlib import Path
from uuid import uuid4

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from lxml import etree
from registry.mappers.cache import GlobalXmlCache, LocalXmlCache
from registry.mappers.configs import XPATH_MAP
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.mappers.xml_mapper import XmlMapper
from registry.models.metadata import DatasetMetadataRecord, Keyword

ISO_DATA = Path(__file__).parent / '../../test_data/iso_metadata'
WMS_SERVICE_XML = ISO_DATA / '../wms-service-metadata.xml'


class MappedValuesShapeTest(TestCase):
    """What mapped_values() and the facade answer for the epic fixtures."""

    def extract(self, path):
        return MDMetadataXmlMapper.extract_mapped_values(path.read_bytes())

    def test_one_record_description_per_md_metadata_node(self):
        records = self.extract(ISO_DATA / "dataset.xml")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["spec"], "dataset")
        self.assertEqual(record["model"], "registry.DatasetMetadataRecord")
        self.assertEqual(record["values"]["file_identifier"],
                         "de.dwd.geoserver.fach.RBSN_FF")
        self.assertEqual(record["values"]["title"],
                         "Windgeschwindigkeit an RBSN Stationen")

    def test_the_two_md_metadata_nodes_of_a_response_are_mapped_independently(
            self):
        root = etree.fromstring((ISO_DATA / "dataset.xml").read_bytes())
        md = root.xpath("//*[local-name()='MD_Metadata']")[0]
        wrapper = etree.Element("wrapper")
        wrapper.append(etree.fromstring(etree.tostring(md)))
        wrapper.append(etree.fromstring(etree.tostring(md)))
        records = MDMetadataXmlMapper.extract_mapped_values(
            etree.tostring(wrapper))
        self.assertEqual(len(records), 2)
        self.assertEqual(
            {r["values"]["file_identifier"] for r in records},
            {"de.dwd.geoserver.fach.RBSN_FF"})

    def test_hierarchy_level_forces_the_config(self):
        """extract_mapped_values answers "map this document with config X"."""
        records = MDMetadataXmlMapper.extract_mapped_values(
            (ISO_DATA / "dataset.xml").read_bytes(),
            hierarchy_level="service")
        self.assertEqual(records[0]["spec"], "service")
        self.assertEqual(records[0]["model"], "registry.ServiceMetadataRecord")
        # a dataset document has no service identification, so the fields
        # below it stay at what the parsed instance carries by default while
        # the root-level ones still map
        self.assertEqual(records[0]["values"]["file_identifier"],
                         "de.dwd.geoserver.fach.RBSN_FF")
        self.assertEqual(records[0]["values"]["title"], "")

    def test_an_unknown_forced_hierarchy_level_raises_like_selection_does(
            self):
        with self.assertRaises(ValueError):
            MDMetadataXmlMapper.extract_mapped_values(
                (ISO_DATA / "dataset.xml").read_bytes(),
                hierarchy_level="nonexistent")

    def test_mapped_values_runs_the_single_traversal_once(self):
        # the config's record spec is anchored at the document root, so the
        # mapper runs on the MD_Metadata node - the same re-parsed node the
        # harvesting from_xml hands its mappers
        root = etree.fromstring((ISO_DATA / "dataset.xml").read_bytes())
        md_root = root.xpath("//*[local-name()='MD_Metadata']")[0]
        mapper = XmlMapper(
            xml=etree.tostring(md_root),
            mapping=XPATH_MAP[("ISO", "dataset")],
            cache=LocalXmlCache())
        first = mapper.mapped_values()
        self.assertEqual(len(mapper.data), 1)
        second = mapper.mapped_values()
        # a second xml_to_django() would append the record again
        self.assertEqual(len(mapper.data), 1)
        self.assertEqual(first["dataset"][0], second["dataset"][0])


class AccessLinkExtractionTest(TestCase):
    """The onLine/CI_OnlineResource evidence of epic #669, mapped only.

    dataset.xml carries its WMS GetCapabilities link first and the WFS
    GetFeature link with typeNames=RBSN_FF second (the lines the epic
    cites); order and original external values must survive mapping untouched.
    """

    @classmethod
    def setUpTestData(cls):
        records = MDMetadataXmlMapper.extract_mapped_values(
            (ISO_DATA / "dataset.xml").read_bytes())
        cls.values = records[0]["values"]

    def test_online_links_are_mapped_in_document_order(self):
        links = self.values["online_links"]
        self.assertEqual(len(links), 2)
        wms, wfs = links
        self.assertTrue(wms["linkage"].startswith(
            "https://maps.dwd.de/geoserver/dwd/RBSN_FF/ows?service=wms"))
        self.assertEqual(wms["protocol"],
                         "OGC:WMS-1.3.0-http-get-capabilities")
        self.assertEqual(wms["function"], "information")
        self.assertEqual(wms["name"], "WMS Capabilities für RBSN_FF")
        self.assertTrue(wfs["linkage"].startswith(
            "https://maps.dwd.de/geoserver/dwd/RBSN_FF/ows?service=wfs"))
        self.assertIn("typeNames=RBSN_FF", wfs["linkage"])
        self.assertEqual(wfs["protocol"],
                         "OGC:WFS-2.0.0-http-get-feature")
        self.assertEqual(wfs["function"], "download")

    def test_missing_fields_answer_none_and_missing_elements_answer_empty(
            self):
        # dataset.xml has no distributor transfer options
        self.assertEqual(self.values["distributor_online_links"], [])
        # service.xml links carry only a linkage - every other field of the
        # dict is present and None, the element itself is not dropped
        records = MDMetadataXmlMapper.extract_mapped_values(
            (ISO_DATA / "service.xml").read_bytes())
        links = records[0]["values"]["online_links"]
        self.assertEqual(len(links), 2)
        for link in links:
            self.assertEqual(
                set(link), {"linkage", "protocol", "application_profile",
                            "name", "description", "function"})
            self.assertTrue(link["linkage"].startswith(
                "https://www.lfu.bayern.de/gdi/wms/geologie/"
                "rohstoff_gewinnungsstellen"))
            self.assertIsNone(link["protocol"])
            self.assertIsNone(link["function"])

    def test_the_protocol_anchor_of_a_gdi_de_record_is_read_by_its_href(self):
        records = MDMetadataXmlMapper.extract_mapped_values(
            WMS_SERVICE_XML.read_bytes())
        links = records[0]["values"]["online_links"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["protocol"],
                         "http://www.opengis.net/def/serviceType/ogc/wms")
        self.assertEqual(links[0]["name"],
                         'Dienst "WMS INSPIRE Verkehrsnetze Hamburg" '
                         '(GetCapabilities)')


class ServiceOperationAndCouplingTest(TestCase):
    """containsOperations, operatesOn and SV_CoupledResource (service config)."""

    def test_service_operations_keep_name_dcp_and_connect_point(self):
        records = MDMetadataXmlMapper.extract_mapped_values(
            (ISO_DATA / "service.xml").read_bytes())
        operations = records[0]["values"]["operations"]
        self.assertEqual(
            [op["operation_name"] for op in operations],
            ["GetCapabilities", "GetFeatureInfo", "GetMap"])
        for op in operations:
            self.assertEqual(op["dcp"], "WebServices")
            self.assertTrue(op["connect_point_linkage"].startswith(
                "https://www.lfu.bayern.de/gdi/wms/geologie/"
                "rohstoff_gewinnungsstellen"))
        self.assertIn("REQUEST=GetCapabilities",
                      operations[0]["connect_point_linkage"])

    def test_operates_on_keeps_uuidref_and_href_apart(self):
        records = MDMetadataXmlMapper.extract_mapped_values(
            WMS_SERVICE_XML.read_bytes())
        self.assertEqual(records[0]["values"]["operates_on"], [{
            "uuidref": "19A39B3A-2D9E-4805-A5E6-56A5CA3EC8CB",
            "href": ("https://registry.gdi-de.org/id/"
                     "de.hh/72796D51-86BC-4343-AE77-85ECAFFACF15"),
        }])

    def test_coupled_resources_keep_identifier_and_operation_name(self):
        records = MDMetadataXmlMapper.extract_mapped_values(
            WMS_SERVICE_XML.read_bytes())
        coupled = records[0]["values"]["coupled_resources"]
        self.assertEqual(len(coupled), 3)
        self.assertEqual(
            {c["identifier"] for c in coupled},
            {"https://registry.gdi-de.org/id/"
             "de.hh/72796D51-86BC-4343-AE77-85ECAFFACF15"})
        for entry in coupled:
            self.assertEqual(
                set(entry),
                {"identifier", "operation_name", "scoped_name"})
            # the fixture carries no scopedName; the key is still answered
            self.assertIsNone(entry["scoped_name"])

    def test_coupling_elements_are_absent_not_broken_on_other_documents(
            self):
        # service.xml is a service record without operatesOn or coupledResource
        records = MDMetadataXmlMapper.extract_mapped_values(
            (ISO_DATA / "service.xml").read_bytes())
        values = records[0]["values"]
        self.assertEqual(values["operates_on"], [])
        self.assertEqual(values["coupled_resources"], [])
        # and the dataset config does not know the service-identification
        # specs at all - they are keyed where the elements can appear
        dataset_values = MDMetadataXmlMapper.extract_mapped_values(
            (ISO_DATA / "dataset.xml").read_bytes())[0]["values"]
        self.assertNotIn("operations", dataset_values)
        self.assertNotIn("operates_on", dataset_values)
        self.assertEqual(dataset_values["online_links"][0]["name"],
                         "WMS Capabilities für RBSN_FF")


class ExtractionSideEffectFreedomTest(TestCase):
    """No PersistenceHandler, no database, no global cache, no network."""

    def test_extraction_touches_no_database_and_no_global_cache(self):
        cache_size_before = len(GlobalXmlCache._data)
        with CaptureQueriesContext(connection) as queries:
            records = MDMetadataXmlMapper.extract_mapped_values(
                (ISO_DATA / "dataset.xml").read_bytes())
        self.assertTrue(records)
        self.assertEqual(len(queries.captured_queries), 0)
        self.assertEqual(len(GlobalXmlCache._data), cache_size_before)

    def test_extraction_needs_no_persistence_of_a_single_row(self):
        # the fixture references none of the db; mapping a real
        # multi-relation record must answer keywords and contacts from the
        # document alone
        records = MDMetadataXmlMapper.extract_mapped_values(
            (ISO_DATA / "dataset.xml").read_bytes())
        values = records[0]["values"]
        self.assertIn({"keyword": "meteorological"}, values["keywords"])
        self.assertEqual(values["metadata_contact"]["name"],
                         "Deutscher Wetterdienst")
        self.assertEqual(values["languages"], [{"value": 110}])

    def test_mapper_created_by_the_persistence_path_still_uses_global_cache(
            self):
        mappers = MDMetadataXmlMapper.from_xml(
            (ISO_DATA / "dataset.xml").read_bytes())
        self.assertIs(mappers[0].cache, GlobalXmlCache)


class MalformedInputTest(TestCase):
    """Extraction crashes exactly like the mapper crashes, no further."""

    def test_malformed_xml_raises_like_the_mapper_does(self):
        broken = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd">'
            b'<gmd:fileIdentifier>')
        with self.assertRaises(etree.XMLSyntaxError):
            MDMetadataXmlMapper.from_xml(broken)
        with self.assertRaises(etree.XMLSyntaxError):
            MDMetadataXmlMapper.extract_mapped_values(broken)

    def test_document_without_md_metadata_raises_like_the_mapper_does(self):
        without_md = b'<?xml version="1.0"?><nothing/>'
        with self.assertRaises(ValueError):
            MDMetadataXmlMapper.from_xml(without_md)
        with self.assertRaises(ValueError):
            MDMetadataXmlMapper.extract_mapped_values(without_md)

    def test_broken_but_well_formed_content_maps_like_the_mapper_does(self):
        """A CI_OnlineResource whose children stay empty maps to None fields;
        the same document goes through the harvesting mapper without
        raising."""
        content = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<gmd:MD_Metadata'
            b' xmlns:gmd="http://www.isotc211.org/2005/gmd"'
            b' xmlns:gco="http://www.isotc211.org/2005/gco">'
            b'<gmd:hierarchyLevel>'
            b'<gmd:MD_ScopeCode codeListValue="dataset"/>'
            b'</gmd:hierarchyLevel>'
            b'<gmd:distributionInfo><gmd:MD_Distribution>'
            b'<gmd:transferOptions><gmd:MD_DigitalTransferOptions>'
            b'<gmd:onLine><gmd:CI_OnlineResource>'
            b'<gmd:linkage/>'
            b'<gmd:protocol><gco:CharacterString nilReason="missing"/>'
            b'</gmd:protocol>'
            b'</gmd:CI_OnlineResource></gmd:onLine>'
            b'</gmd:MD_DigitalTransferOptions></gmd:transferOptions>'
            b'</gmd:MD_Distribution></gmd:distributionInfo>'
            b'</gmd:MD_Metadata>')
        records = MDMetadataXmlMapper.extract_mapped_values(content)
        link = records[0]["values"]["online_links"][0]
        self.assertIsNone(link["linkage"])
        self.assertIsNone(link["protocol"])


class MappedValuesMatchPersistenceTest(TestCase):
    """One interpretation: the persisted record carries exactly the values
    the extraction answered - persistence consumes the same mapped
    representation, it does not read the XML a second time differently."""

    @classmethod
    def setUpTestData(cls):
        content = (ISO_DATA / "dataset.xml").read_bytes()
        cls.mapped = MDMetadataXmlMapper.extract_mapped_values(
            content)[0]["values"]
        mappers = MDMetadataXmlMapper.from_xml(content)
        mappers[0].xml_to_django()
        handler = PersistenceHandler(
            mapper=mappers[0],
            defaults={
                "dataset": {"origin": 1, "origin_url": "http://localhost"}})
        handler.persist_all()
        cls.record = DatasetMetadataRecord.objects.get(
            file_identifier=cls.mapped["file_identifier"])

    def test_flat_fields_agree(self):
        for field in ("title", "abstract", "access_constraints",
                      "code", "code_space"):
            with self.subTest(field=field):
                self.assertEqual(getattr(self.record, field),
                                 self.mapped[field])

    def test_parsed_relations_agree(self):
        self.assertEqual(
            sorted(self.record.keywords.values_list("keyword", flat=True)),
            sorted(k["keyword"] for k in self.mapped["keywords"]))
        self.assertEqual(
            sorted(self.record.languages.values_list("value", flat=True)),
            sorted(lang["value"] for lang in self.mapped["languages"]))
        self.assertEqual(
            self.record.categories.count(),
            len(self.mapped["categories"]))

    def test_date_stamp_agrees_as_instants(self):
        self.assertEqual(self.record.date_stamp, self.mapped["date_stamp"])


class NoPersistenceOfAccessElementsTest(TestCase):
    """#983 persists these elements; #981 only maps them."""

    def test_no_model_and_no_column_carries_the_access_elements(self):
        field_names = {
            f.name for f in DatasetMetadataRecord._meta.get_fields()}
        for spec_key in ("online_links", "distributor_online_links",
                         "operations", "operates_on", "coupled_resources"):
            self.assertNotIn(spec_key, field_names)

    def test_value_specs_are_ignored_by_the_reverse_serialization(self):
        """The reverse path has no _reverse_parser for a value spec - it must
        leave the document untouched rather than write the dict anywhere."""
        root = etree.Element("root")
        element = etree.SubElement(root, "child")
        element.text = "untouched"
        mapper = XmlMapper(
            xml=root, mapping=XPATH_MAP[("ISO", "dataset")])
        mapper.sync_field_to_xml(
            root, "online_links",
            XPATH_MAP[("ISO", "dataset")]["dataset"]["fields"]["online_links"],
            DatasetMetadataRecord())
        self.assertEqual(etree.tostring(root).decode(),
                         "<root><child>untouched</child></root>")


class LocalXmlCacheTest(TestCase):
    """The local cache answers the call surface the mapper relies on."""

    def test_roundtrip(self):
        cache = LocalXmlCache()
        uid = uuid4()
        self.assertEqual(cache.get(uid, []), [])
        cache.set(f"{uid}:a", "value")
        cache.add_to_list(uid, f"{uid}:a")
        self.assertEqual(cache.get(f"{uid}:a"), "value")
        self.assertEqual(cache.get_many([f"{uid}:a", f"{uid}:b"]),
                         {f"{uid}:a": "value", f"{uid}:b": None})
        cache.delete(f"{uid}:a")
        self.assertIsNone(cache.get(f"{uid}:a"))
        self.assertEqual(cache.get(uid, []), [])
        keyword = Keyword(keyword="x")
        cache.set("k", keyword)
        self.assertIs(cache.get("k"), keyword)
