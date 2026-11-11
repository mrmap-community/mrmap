from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from django.test import TestCase
from lxml import etree
from registry.enums.iso import CategoryChoices
from registry.enums.metadata import ReferenceSystemPrefixChoices
from registry.mappers.factory import MDMetadataXmlMapper, OGCServiceXmlMapper
from registry.mappers.parsers.iso import (parse_reference_system,
                                          parse_topic_category)
from registry.mappers.persistence.handler import PersistenceHandler
from registry.mappers.xml_mapper import XmlMapper
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      ServiceMetadataRecord)
from registry.models.service import (CatalogueService, FeatureType,
                                     OperationUrl, WebFeatureService,
                                     WebMapService)
from tests.django.test_data.capabilities.csw.expected_service_data import \
    EXPECTED_DATA as EXPECTED_CSW_SERVICE_DATA_2_0_2
from tests.django.test_data.capabilities.wfs.expected_featuretype_data import \
    EXPECTED_DATA as FEATURETYPE_DATA_2_0_0
from tests.django.test_data.capabilities.wfs.expected_service_data import \
    EXPECTED_DATA as EXPECTED_WFS_SERVICE_DATA_2_0_0
from tests.django.test_data.capabilities.wms.expected_layer_data_111 import \
    LAYER_DATA as LAYER_DATA_1_1_1
from tests.django.test_data.capabilities.wms.expected_layer_data_130 import \
    LAYER_DATA as LAYER_DATA_1_3_0
from tests.django.test_data.capabilities.wms.expected_service_data_111 import \
    EXPECTED_DATA as EXPECTED_WMS_SERVICE_DATA_1_1_1
from tests.django.test_data.capabilities.wms.expected_service_data_130 import \
    EXPECTED_DATA as EXPECTED_WMS_SERVICE_DATA_1_3_0
from tests.django.test_data.iso_metadata.expected_dataset_data import \
    EXPECTED_DATA as EXPECTED_DATASET_DATA
from tests.django.test_data.iso_metadata.expected_service_data import \
    EXPECTED_DATA as EXPECTED_SERVICE_DATA


def group_and_accumulate(rows, key_fields, accumulate_fields):
    """
    rows: iterable von Tupeln (z. B. values_list(...))
    key_fields: Liste der Felder, die als Schlüssel dienen
    accumulate_fields: Liste der Felder, deren Werte gesammelt werden sollen
    """
    grouped = defaultdict(lambda: defaultdict(list))

    # --- Gruppieren ---
    for row in rows:
        # row von Tupel -> dict
        row_map = {field: value for field, value in zip(
            key_fields + accumulate_fields, row)}

        key = tuple(row_map[field] for field in key_fields)

        for acc_field in accumulate_fields:
            val = row_map.get(acc_field)
            if val:
                grouped[key][acc_field].append(val)
            else:
                grouped[key][acc_field]

    # --- Rückgabe ---
    result = []

    for key, acc_data in grouped.items():
        if len(accumulate_fields) == 1:
            # nur EIN Akkufeld -> flatten wie im Beispiel
            only_field = accumulate_fields[0]
            result.append((*key, acc_data[only_field]))
        else:
            # mehrere -> dict wie gewohnt
            result.append((*key, {f: acc_data[f] for f in accumulate_fields}))

    return result


class XmlMapperTest(TestCase):

    def __export_parsed_wfs_data(self, data):
        """helper function to generate featuretype specific expected data"""
        expected_layer_data = {
            item.identifier: {
                "title": item.title,
                "abstract": item.abstract,
                "bbox_lat_lon": item.bbox_lat_lon.wkt if item.bbox_lat_lon else None,
                "output_formats": list(item.output_formats.values_list("mime_type", flat=True)),
                "keywords": list(item.keywords.values_list("keyword", flat=True)),
                "reference_systems": list(item.reference_systems.values_list("code", flat=True)),
            }
            for item in data
        }

        import pprint
        from pathlib import Path
        file_path = Path(f"expected_data_{uuid4()}.py")

        # Dictionary als Python-Code in die Datei schreiben
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("EXPECTED_DATA = ")
            f.write(pprint.pformat(expected_layer_data, indent=4))

    def __export_parsed_service_data(self, data):
        """helper function to generate service specific expected data"""
        service = data[0]

        # Zuerst alle Operation-URL-Zeilen holen:
        raw_ops = service.operation_urls.values_list(
            "method", "operation", "url", "mime_types__mime_type"
        )

        operation_urls = group_and_accumulate(
            rows=raw_ops,
            key_fields=["method", "operation", "url"],
            accumulate_fields=["mime_types__mime_type"],
        )

        expected_data = {
            "title": service.title,
            "abstract": service.abstract,
            "operation_urls": operation_urls,
            "keywords": list(service.keywords.values_list("keyword", flat=True)),
        }

        import pprint
        from pathlib import Path
        file_path = Path(f"expected_data_{uuid4()}.py")

        # Dictionary als Python-Code in die Datei schreiben
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("EXPECTED_DATA = ")
            f.write(pprint.pformat(expected_data, indent=4))

    def __export_parsed_metadata(self, data):
        """helper function to generate service specific expected data"""
        md = data[0]

        expected_data = {
            "title": md.title,
            "abstract": md.abstract,
            "date_stamp": str(md.date_stamp),
            "access_constraints": md.access_constraints,
            "file_identifier": md.file_identifier,
            "language": md.language,
            "bounding_geometry": md.bounding_geometry.wkt if md.bounding_geometry else None,
            "keywords": list(md.keywords.values_list("keyword", flat=True)),
            "reference_systems": list(md.reference_systems.values_list("code", flat=True)),
        }

        import pprint
        from pathlib import Path
        file_path = Path(f"expected_data_{uuid4()}.py")

        # Dictionary als Python-Code in die Datei schreiben
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("EXPECTED_DATA = ")
            f.write(pprint.pformat(expected_data, indent=4))

    def _call_service_mapper_and_persistence_handler(self):
        """Test that create manager function works correctly."""
        mapper = OGCServiceXmlMapper.from_xml(self.xml)
        self.data = mapper.xml_to_django()
        handler = PersistenceHandler(mapper)
        handler.persist_all()

    def _call_iso_mapper_and_persistence_handler(self):
        """Test that create manager function works correctly."""
        mappers = MDMetadataXmlMapper.from_xml(self.xml)
        self.data = mappers[0].xml_to_django()
        # self.__export_parsed_metadata(self.data)
        handler = PersistenceHandler(mappers[0])
        handler.persist_all()

    def _test_service_success(self, expected):
        service = self.data[0]

        self.assertEqual(service.title, expected["title"])
        self.assertEqual(
            service.abstract, expected["abstract"])

        db_keywords = list(service.keywords.values_list('keyword', flat=True))
        self.assertCountEqual(
            db_keywords, expected["keywords"], f"SERVICE hat falsche Keywords")

        raw_ops = service.operation_urls.values_list(
            "method", "operation", "url", "mime_types__mime_type"
        )

        operation_urls = group_and_accumulate(
            rows=raw_ops,
            key_fields=["method", "operation", "url"],
            accumulate_fields=["mime_types__mime_type"],
        )

        self.assertCountEqual([(op[0], op[1], op[2], op[3].sort()) for op in operation_urls], [(op[0], op[1], op[2], op[3].sort()) for op in expected["operation_urls"]],
                              f"SERVICE hat falsche OperationUrls")

        db_metadata_url = list(
            service.remote_metadata.values_list('link', flat=True))
        self.assertCountEqual([str(c) for c in db_metadata_url], [str(c) for c in expected.get("remote_metadata", [])],
                              f"Service hat falsche RemoteMetadata")

    def _test_md_success(self, expected):
        md = self.data[0]

        self.assertEqual(md.title, expected["title"])
        self.assertEqual(md.abstract, expected["abstract"])
        self.assertEqual(str(md.date_stamp), expected["date_stamp"])
        self.assertEqual(md.file_identifier, expected["file_identifier"])

        db_languages = list(md.languages.values_list('value', flat=True))
        self.assertCountEqual(
            db_languages, expected["languages"], f"MetadataRecord hat falsche languages")

        db_keywords = list(md.keywords.values_list('keyword', flat=True))
        self.assertCountEqual(
            db_keywords, expected["keywords"], f"MetadataRecord hat falsche Keywords")

        db_categories = list(md.categories.values_list(
            'value', flat=True) if hasattr(md, 'categories') else [])
        self.assertCountEqual(
            db_categories, expected.get("categories", []), f"MetadataRecord hat falsche Categories")

        db_time_extents = list(str(extent) for extent in md.time_extents.all())
        self.assertCountEqual(
            db_time_extents, expected["time_extents"], f"MetadataRecord hat falsche time extents")

        # ReferenceSystems prüfen
        db_crs = list(
            md.reference_systems.values_list('code', flat=True))
        self.assertCountEqual([str(c) for c in db_crs], [str(c) for c in expected["reference_systems"]],
                              f"MetadataRecord {md.file_identifier} hat falsche ReferenceSystems")

    def _test_wms_success(self, expected):
        wms = self.data[0]

        db_layers = wms.layers.all()

        self.assertEqual(len(expected), len(db_layers))

        for layer in db_layers:
            self.assertIn(layer.identifier, expected,
                          f"Layer {layer.identifier} ist nicht in den erwateten Layern")

            _expected = expected[layer.identifier]

            # Title und Abstract prüfen
            self.assertEqual(
                layer.title, _expected["title"], f"Layer {layer.identifier} hat falschen Title")
            self.assertEqual(
                layer.abstract, _expected["abstract"], f"Layer {layer.identifier} hat falschen Abstract")
            self.assertEqual(
                layer.is_queryable, _expected["is_queryable"], f"Layer {layer.identifier} hat falschen queryable")
            self.assertEqual(
                layer.is_opaque, _expected["is_opaque"], f"Layer {layer.identifier} hat falschen opaque")
            self.assertEqual(
                layer.is_cascaded, _expected["is_cascaded"], f"Layer {layer.identifier} hat falschen cascaded")
            self.assertEqual(
                layer.bbox_lat_lon.wkt if layer.bbox_lat_lon else None, _expected["bbox_lat_lon"], f"Layer {layer.identifier} hat falsche bbox")

            # Keywords prüfen
            db_keywords = list(
                layer.keywords.values_list('keyword', flat=True))
            self.assertCountEqual(
                db_keywords, _expected["keywords"], f"Layer {layer.identifier} hat falsche Keywords")

            # ReferenceSystems prüfen
            db_crs = list(
                layer.reference_systems.values_list('code', flat=True))
            self.assertCountEqual([str(c) for c in db_crs], [str(c) for c in _expected["reference_systems"]],
                                  f"Layer {layer.identifier} hat falsche ReferenceSystems")

            # LayerMetadataUrl prüfen
            db_metadata_url = list(
                layer.remote_metadata.values_list('link', flat=True))
            self.assertCountEqual([str(c) for c in db_metadata_url], [str(c) for c in _expected.get("remote_metadata", [])],
                                  f"Layer {layer.identifier} hat falsche RemoteMetadata")

    def _test_wfs_success(self):
        wfs = self.data[0]
        db_featuretypes = wfs.featuretypes.all()

        self.assertEqual(len(FEATURETYPE_DATA_2_0_0), len(db_featuretypes))

        for featuretype in db_featuretypes:
            self.assertIn(featuretype.identifier, FEATURETYPE_DATA_2_0_0,
                          f"FeatureType {featuretype.identifier} ist nicht in den erwateten FeatureTypes")

            expected = FEATURETYPE_DATA_2_0_0[featuretype.identifier]

            # Title und Abstract prüfen
            self.assertEqual(
                featuretype.title, expected["title"], f"FeatureType {featuretype.identifier} hat falschen Title")
            self.assertEqual(
                featuretype.abstract, expected["abstract"], f"FeatureType {featuretype.identifier} hat falschen Abstract")
            self.assertEqual(
                featuretype.bbox_lat_lon.wkt if featuretype.bbox_lat_lon else None, expected["bbox_lat_lon"], f"FeatureType {featuretype.identifier} hat falsche bbox")

            # Keywords prüfen
            db_keywords = list(
                featuretype.keywords.values_list('keyword', flat=True))
            self.assertCountEqual(
                db_keywords, expected["keywords"], f"FeatureType {featuretype.identifier} hat falsche Keywords")

            # ReferenceSystems prüfen
            db_crs = list(
                featuretype.reference_systems.values_list('code', flat=True))
            self.assertCountEqual([str(c) for c in db_crs], [str(c) for c in expected["reference_systems"]],
                                  f"FeatureType {featuretype.identifier} hat falsche ReferenceSystems")

            # FeatureTypeMetadataUrl prüfen
            db_metadata_url = list(
                featuretype.remote_metadata.values_list('link', flat=True))
            self.assertCountEqual([str(c) for c in db_metadata_url], [str(c) for c in expected.get("remote_metadata", [])],
                                  f"FeatureType {featuretype.identifier} hat falsche RemoteMetadata")

    def test_wms_1_1_1(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wms/1.1.1.xml'))
        self._call_service_mapper_and_persistence_handler()
        self._test_service_success(expected=EXPECTED_WMS_SERVICE_DATA_1_1_1)
        self._test_wms_success(expected=LAYER_DATA_1_1_1)

    def test_wms_1_3_0(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wms/1.3.0.xml'))
        self._call_service_mapper_and_persistence_handler()
        self._test_service_success(expected=EXPECTED_WMS_SERVICE_DATA_1_3_0)
        self._test_wms_success(expected=LAYER_DATA_1_3_0)

    def test_wfs_2_0_0(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/wfs/2.0.0.xml'))
        self._call_service_mapper_and_persistence_handler()
        # self.__export_parsed_wfs_data(self.data[0].featuretypes.all())
        self._test_service_success(expected=EXPECTED_WFS_SERVICE_DATA_2_0_0)
        self._test_wfs_success()

    def test_hamburg_wfs_featuretypes(self):
        contact = MetadataContact.objects.create(name='Existing contact')
        existing = WebFeatureService.objects.create(
            title='Z existing WFS', version=200,
            metadata_contact=contact, service_contact=contact,
        )
        self.xml = Path(__file__).parent / '../../test_data/capabilities/wfs/hamburg_2.0.0.xml'
        self._call_service_mapper_and_persistence_handler()
        service = self.data[0]
        self.assertCountEqual(
            service.featuretypes.values_list('identifier', flat=True),
            ['cp:CadastralParcel', 'cp:CadastralZoning'],
        )
        self.assertEqual(existing.featuretypes.count(), 0)
        self.assertEqual(existing.operation_urls.count(), 0)
        self.assertTrue(service.operation_urls.exists())
        self.assertTrue(service.remote_metadata.exists())
        self.assertEqual(service.change_log.count(), 2)

    def test_csw_2_0_2(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/capabilities/csw/2.0.2.xml'))
        self._call_service_mapper_and_persistence_handler()
        self._test_service_success(expected=EXPECTED_CSW_SERVICE_DATA_2_0_2)

    def test_iso_dataset(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/iso_metadata/dataset.xml'))
        self._call_iso_mapper_and_persistence_handler()
        self._test_md_success(expected=EXPECTED_DATASET_DATA)

    def test_iso_service(self):
        self.xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/iso_metadata/service.xml'))
        self._call_iso_mapper_and_persistence_handler()
        self._test_md_success(expected=EXPECTED_SERVICE_DATA)

    def __iso_service_without_point_of_contact(self, with_metadata_contact):
        """The service fixture names its responsible party in the service
        identification. Many catalogues name it in gmd:contact only and leave
        the point of contact away, which answers the same record without it.

        The gmd:contact of the fixture is an empty placeholder element.
        """
        xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/iso_metadata/service.xml'))
        namespaces = {'gmd': 'http://www.isotc211.org/2005/gmd'}
        root = etree.fromstring(xml.read_bytes())
        point_of_contact = root.find(
            ".//gmd:identificationInfo//gmd:pointOfContact", namespaces)
        if with_metadata_contact:
            responsible_party = point_of_contact.find(
                "gmd:CI_ResponsibleParty", namespaces)
            # serializing the element keeps the namespaces it is declared with
            root.find(".//gmd:MD_Metadata/gmd:contact", namespaces).append(
                etree.fromstring(etree.tostring(responsible_party)))
        point_of_contact.getparent().remove(point_of_contact)
        return root

    def test_iso_service_without_point_of_contact_uses_gmd_contact(self):
        """A service record which names its responsible party in gmd:contact
        only is imported with that contact instead of being dropped."""
        self.xml = self.__iso_service_without_point_of_contact(
            with_metadata_contact=True)
        self._call_iso_mapper_and_persistence_handler()
        record = ServiceMetadataRecord.objects.get(
            file_identifier='ee065040-1015-44c7-839e-e8e349c74bbd')
        self.assertEqual(
            record.metadata_contact.name, 'Bayerisches Landesamt für Umwelt')

    def test_iso_service_without_any_responsible_party(self):
        """A record without any responsible party can not be stored, because a
        metadata contact is required. It is answered by an error which names
        the record and the field, not by an exception of the ORM."""
        self.xml = self.__iso_service_without_point_of_contact(
            with_metadata_contact=False)
        with self.assertRaises(ValueError) as context:
            self._call_iso_mapper_and_persistence_handler()
        error = str(context.exception)
        self.assertIn("ServiceMetadataRecord", error)
        self.assertIn("ee065040-1015-44c7-839e-e8e349c74bbd", error)
        self.assertIn("has no 'metadata_contact'", error)
        self.assertFalse(
            ServiceMetadataRecord.objects.filter(
                file_identifier='ee065040-1015-44c7-839e-e8e349c74bbd').exists())

    def test_iso_dataset_without_metadata_contact_uses_point_of_contact(self):
        """A dataset record which has no gmd:contact is imported with the party
        which provides the data instead of being dropped."""
        xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(),
            '../../test_data/iso_metadata/dataset.xml'))
        namespaces = {'gmd': 'http://www.isotc211.org/2005/gmd'}
        root = etree.fromstring(xml.read_bytes())
        metadata_contact = root.find(
            ".//gmd:MD_Metadata/gmd:contact", namespaces)
        metadata_contact.getparent().remove(metadata_contact)
        self.xml = root
        self._call_iso_mapper_and_persistence_handler()
        record = DatasetMetadataRecord.objects.get(
            file_identifier='de.dwd.geoserver.fach.RBSN_FF')
        self.assertEqual(record.dataset_contact.name, 'Deutscher Wetterdienst')
        self.assertEqual(record.metadata_contact, record.dataset_contact)

    def _test_iso_reversed_time_extent(self, keep_valid_extent):
        for filename in ('dataset.xml', 'service.xml'):
            with self.subTest(filename=filename):
                xml = Path(__file__).parent / '../../test_data/iso_metadata' / filename
                mapper = MDMetadataXmlMapper.from_xml(xml)[0]
                namespaces = mapper.mapping['_namespaces']
                extent = mapper.xml_root.find('.//gmd:EX_TemporalExtent/gmd:extent', namespaces)
                period = extent.find('gml:TimePeriod', namespaces)
                begin = period.find('gml:beginPosition', namespaces)
                end = period.find('gml:endPosition', namespaces)
                end.attrib.clear()
                begin.text = '2016-02-01'
                end.text = '2014-12-31'
                if keep_valid_extent:
                    valid_extent = deepcopy(extent)
                    valid_period = valid_extent.find('gml:TimePeriod', namespaces)
                    valid_period.find('gml:beginPosition', namespaces).text = '2014-12-31'
                    extent.getparent().append(valid_extent)

                record = mapper.xml_to_django()[0]
                self.assertEqual(mapper.warnings, [
                    'Skipped temporal extent because begin 2016-02-01 is after end 2014-12-31.',
                ])
                PersistenceHandler(mapper).persist_all()
                record.refresh_from_db()
                self.assertTrue(record.title)
                extents = list(record.time_extents.all())
                self.assertEqual(len(extents), int(keep_valid_extent))
                if keep_valid_extent:
                    self.assertEqual(extents[0].begin, datetime(2014, 12, 31, tzinfo=UTC))
                    self.assertEqual(extents[0].end, datetime(2014, 12, 31, tzinfo=UTC))

    def test_iso_import_skips_reversed_time_extent(self):
        self._test_iso_reversed_time_extent(keep_valid_extent=False)

    def test_iso_import_keeps_valid_extent_alongside_reversed_extent(self):
        self._test_iso_reversed_time_extent(keep_valid_extent=True)

    # One MD_Resolution block with one representative fraction, the shape ISO
    # 19139 allows per part of a dataset and which an inventory mapping several
    # scales uses (#990).
    RESOLUTION = """
    <gmd:spatialResolution xmlns:gmd="http://www.isotc211.org/2005/gmd"
                           xmlns:gco="http://www.isotc211.org/2005/gco">
      <gmd:MD_Resolution>
        <gmd:equivalentScale>
          <gmd:MD_RepresentativeFraction>
            <gmd:denominator><gco:Integer>{}</gco:Integer></gmd:denominator>
          </gmd:MD_RepresentativeFraction>
        </gmd:equivalentScale>
      </gmd:MD_Resolution>
    </gmd:spatialResolution>
    """

    def __with_representative_fractions(self, filename, denominators):
        """The ISO fixture with one resolution block per given denominator.

        Neither fixture carries a spatial resolution at all, so the blocks are
        added to the identification of the record - before its extent, where
        ISO 19139 places the resolution of a record.
        """
        xml = Path(__file__).parent / '../../test_data/iso_metadata' / filename
        namespaces = {'gmd': 'http://www.isotc211.org/2005/gmd'}
        root = etree.fromstring(xml.read_bytes())
        identification = root.xpath(
            './/gmd:identificationInfo/*', namespaces=namespaces)[0]
        extent = identification.find('gmd:extent', namespaces)
        position = list(identification).index(
            extent) if extent is not None else len(identification)
        for offset, denominator in enumerate(denominators):
            identification.insert(
                position + offset,
                etree.fromstring(self.RESOLUTION.format(denominator)))
        return root

    def test_iso_import_keeps_first_of_several_representative_fractions(self):
        """A record which maps several scales answers one denominator per
        resolution block. The scalar equivalent_scale is answered by the first
        one and the record is imported: answering it with the list of all
        denominators was refused by the field on save and cost the whole record
        (#990). The dropped denominator is named in the warnings, so the
        harvesting run says which scale it left behind."""
        for filename in ('dataset.xml', 'service.xml'):
            with self.subTest(filename=filename):
                mapper = MDMetadataXmlMapper.from_xml(
                    self.__with_representative_fractions(
                        filename, ('30000', '75000')))[0]

                record = mapper.xml_to_django()[0]
                self.assertEqual(mapper.warnings, [
                    "Mapped 2 values for the single valued field "
                    "'equivalent_scale'; kept '30000' and dropped ['75000'].",
                ])
                PersistenceHandler(mapper).persist_all()
                record.refresh_from_db()

                self.assertTrue(record.title)
                self.assertEqual(record.equivalent_scale, 30000.0)

    def test_iso_import_maps_a_single_representative_fraction_unreported(self):
        """The value of a record which names exactly one scale is mapped
        without a word about it - the mapper only speaks about the values it
        really dropped."""
        for filename in ('dataset.xml', 'service.xml'):
            with self.subTest(filename=filename):
                mapper = MDMetadataXmlMapper.from_xml(
                    self.__with_representative_fractions(
                        filename, ('25000',)))[0]

                record = mapper.xml_to_django()[0]
                self.assertEqual(mapper.warnings, [])
                PersistenceHandler(mapper).persist_all()
                record.refresh_from_db()

                self.assertEqual(record.equivalent_scale, 25000.0)


class SingleValueOfAMultiValuedXpathTest(TestCase):
    """The two cases of #990 which no document produces: a column which holds a
    list itself, and a parse which matched nothing at all. Neither is answered
    by picking a value out of the other one."""

    def mapper(self):
        return XmlMapper(xml=b"<xml/>", mapping={})

    def test_a_field_whose_column_holds_a_list_keeps_the_list(self):
        """`keywords_list` is an ArrayField - the list IS its value, so nothing
        may be picked out of it and nothing is reported."""
        mapper = self.mapper()

        values = mapper.single_value_for_field(
            "keywords_list", DatasetMetadataRecord(), ['30000', '75000'])

        self.assertEqual(values, ['30000', '75000'])
        self.assertEqual(mapper.warnings, [])

    def test_an_empty_match_of_a_single_valued_field_answers_no_value(self):
        """Nothing matched, so nothing is set and nothing was dropped - a
        warning here would report a loss which did not happen."""
        mapper = self.mapper()

        self.assertIsNone(mapper.single_value_for_field(
            "equivalent_scale", DatasetMetadataRecord(), []))
        self.assertEqual(mapper.warnings, [])


class ServiceOwnershipRegressionTest(TestCase):
    """Registering a second service must not redirect the operation urls,
    feature types or layers of a capabilities document to another published
    service.

    The ambiguous natural-key lookup that caused this selected the nullable
    unique ``update_candidate_of`` field (see #659 and #661): all published
    services share the NULL value and collapse under the same key. The tests
    control the model ordering, which decides which NULL-key row wins an
    unordered lookup, so an adverse ordering is exercised deterministically.
    That ordering is a test control, not a production configuration.
    """

    CAPABILITIES = Path(__file__).parent / '../../test_data/capabilities'
    SECOND_URL = "https://second.example.test/service"

    def _adverse_ordering(self, model_cls):
        original_ordering = model_cls._meta.ordering
        self.addCleanup(setattr, model_cls._meta, "ordering", original_ordering)
        model_cls._meta.ordering = ["title"]

    def _register(self, xml_path, title, rename_children=False):
        mapper = OGCServiceXmlMapper.from_xml(xml_path)
        service = mapper.xml_to_django()[0]
        service.title = title
        if rename_children:
            for inst in mapper.read_all_from_cache().values():
                if inst is None:
                    continue
                if isinstance(inst, OperationUrl):
                    inst.url = self.SECOND_URL
                elif isinstance(inst, FeatureType):
                    inst.identifier = "second_" + inst.identifier
        PersistenceHandler(mapper).persist_all()
        return service

    def _assert_owned_operation_urls(self, first, second):
        """Both services own the operation urls of their own document.

        ``operation_urls`` is the relationship the API answers for a service,
        so agreeing with the database rows here means the API relationship
        agrees with the owning service id as well.
        """
        self.assertGreater(second.operation_urls.count(), 0)
        self.assertEqual(
            first.operation_urls.count(), second.operation_urls.count())
        self.assertCountEqual(
            set(second.operation_urls.values_list("url", flat=True)),
            {self.SECOND_URL})
        self.assertNotIn(
            self.SECOND_URL, set(first.operation_urls.values_list("url", flat=True)))
        first_rows = {
            (row["method"], row["operation"], row["mime_types__mime_type"])
            for row in first.operation_urls.values("method", "operation", "mime_types__mime_type")}
        second_rows = {
            (row["method"], row["operation"], row["mime_types__mime_type"])
            for row in second.operation_urls.values("method", "operation", "mime_types__mime_type")}
        self.assertEqual(first_rows, second_rows)
        # every row advertising the second endpoint belongs to the second
        # service; the endpoint text alone must not own rows of another
        # service (the deployment seeds its own CSW, so no global count here).
        model_cls = first.operation_urls.model
        second_owned = model_cls.objects.filter(url=self.SECOND_URL)
        self.assertEqual(
            second_owned.count(), second.operation_urls.count())
        self.assertCountEqual(
            set(second_owned.values_list("service_id", flat=True)), {second.pk})

    def test_wfs_2_0_0_second_service_keeps_operation_urls(self):
        self._adverse_ordering(WebFeatureService)
        first = self._register(self.CAPABILITIES / 'wfs/2.0.0.xml', 'ZZZ first service')
        second = self._register(
            self.CAPABILITIES / 'wfs/2.0.0.xml', 'AAA second service', rename_children=True)

        self._assert_owned_operation_urls(first, second)
        self.assertGreater(first.featuretypes.count(), 0)
        self.assertEqual(first.featuretypes.count(), second.featuretypes.count())
        self.assertCountEqual(
            second.featuretypes.values_list("identifier", flat=True),
            ["second_" + ident for ident in first.featuretypes.values_list("identifier", flat=True)])

    def test_wms_1_3_0_second_service_keeps_operation_urls(self):
        self._adverse_ordering(WebMapService)
        first = self._register(self.CAPABILITIES / 'wms/1.3.0.xml', 'ZZZ first service')
        second = self._register(
            self.CAPABILITIES / 'wms/1.3.0.xml', 'AAA second service', rename_children=True)

        self._assert_owned_operation_urls(first, second)
        self.assertGreater(first.layers.count(), 0)
        self.assertEqual(first.layers.count(), second.layers.count())

    def test_wms_1_1_1_second_service_keeps_operation_urls(self):
        self._adverse_ordering(WebMapService)
        first = self._register(self.CAPABILITIES / 'wms/1.1.1.xml', 'ZZZ first service')
        second = self._register(
            self.CAPABILITIES / 'wms/1.1.1.xml', 'AAA second service', rename_children=True)

        self._assert_owned_operation_urls(first, second)
        self.assertGreater(first.layers.count(), 0)
        self.assertEqual(first.layers.count(), second.layers.count())

    def test_csw_2_0_2_second_service_keeps_operation_urls(self):
        self._adverse_ordering(CatalogueService)
        first = self._register(self.CAPABILITIES / 'csw/2.0.2.xml', 'ZZZ first service')
        second = self._register(
            self.CAPABILITIES / 'csw/2.0.2.xml', 'AAA second service', rename_children=True)

        self._assert_owned_operation_urls(first, second)


class TopicCategoryEmptyElementRegressionTest(TestCase):
    """An empty <gmd:MD_TopicCategoryCode/> is a missing value, not an import
    error (#989).

    Of the 146 GDI-BW records one harvest could not import, four fifths carried
    the topic category code without any character content. The parser called
    .strip() on the None lxml answers for such an element's text, and that
    AttributeError aborted the mapping of the whole record. Whatever the parser
    decides about a category it cannot read, it may cost the category at most,
    never the record.
    """

    XML = Path(__file__).parent / '../../test_data/iso_metadata/dataset.xml'
    NAMESPACES = {'gmd': 'http://www.isotc211.org/2005/gmd'}

    def _record_with_empty_topic_category(self, text):
        """The dataset fixture with its category code carrying `text`."""
        root = etree.fromstring(self.XML.read_bytes())
        root.find('.//gmd:MD_TopicCategoryCode', self.NAMESPACES).text = text
        mapper = MDMetadataXmlMapper.from_xml(root)[0]
        mapper.xml_to_django()
        PersistenceHandler(mapper).persist_all()
        return DatasetMetadataRecord.objects.get(
            file_identifier='de.dwd.geoserver.fach.RBSN_FF')

    def test_an_empty_topic_category_element_costs_the_category_only(self):
        # the element carries no character content: lxml gives None for its text
        for text in (None, "\n            "):
            with self.subTest(text=text):
                record = self._record_with_empty_topic_category(text)
                self.assertEqual(record.title, EXPECTED_DATASET_DATA["title"])
                self.assertFalse(
                    record.categories.exists(),
                    "the unusable category must not produce a row")
                # the rest of the record is untouched
                self.assertTrue(record.keywords.exists())
                self.assertTrue(record.languages.exists())
                self.assertIsNotNone(record.bounding_geometry)

    def test_a_valid_topic_category_still_maps_after_the_fix(self):
        record = self._record_with_empty_topic_category("biota")
        self.assertCountEqual(
            record.categories.values_list('value', flat=True),
            [CategoryChoices.BIOTA.value])


class ParseTopicCategoryNodeTest(TestCase):
    """The parser's contract on the two node types its signature names (#989).

    An element without character content answers like the empty case of the
    character branch: CategoryChoices('') is no valid choice, so the answer is
    None and the mapping of the record continues.
    """

    def _element(self, text):
        """A category code element carrying `text` as its character content;
        None builds the empty <MD_TopicCategoryCode/> of the issue."""
        ns = 'xmlns:gmd="http://www.isotc211.org/2005/gmd"'
        if text is None:
            xml = f'<gmd:MD_TopicCategoryCode {ns}/>'
        else:
            xml = (f'<gmd:MD_TopicCategoryCode {ns}>{text}'
                   '</gmd:MD_TopicCategoryCode>')
        return etree.fromstring(xml.encode())

    def test_element_without_character_content_answers_none(self):
        for text in (None, "", "  \n "):
            with self.subTest(text=text):
                self.assertIsNone(
                    parse_topic_category(None, self._element(text)))

    def test_empty_text_node_answers_none(self):
        element = self._element("anything")
        element.text = ""
        text_node = element.xpath("./text()")[0]
        self.assertIsNone(parse_topic_category(None, text_node))

    def test_valid_and_unknown_codes_answer_as_before(self):
        self.assertEqual(
            parse_topic_category(None, self._element("biota")).value,
            CategoryChoices.BIOTA.value)
        self.assertIsNone(
            parse_topic_category(None, self._element("no category defined till now!")))


class ReferenceSystemEmptyElementRegressionTest(TestCase):
    """An empty <gco:CharacterString/> of a reference system is a missing
    value, not an import error (#1074).

    This is #989 one function further up in the same parser module: the
    reference system spec of the metadata mapping selects the character string
    below <gmd:code> and hands it to the parser, which called .strip() on the
    None lxml answers for an element without character content. The exception
    travelled out of the mapping and aborted the import of the whole record, so
    one cosmetically empty element cost the record. An empty element costs its
    own reference system at most, never the record.
    """

    XML = Path(__file__).parent / '../../test_data/iso_metadata/dataset.xml'
    NAMESPACES = {'gmd': 'http://www.isotc211.org/2005/gmd',
                  'gco': 'http://www.isotc211.org/2005/gco'}
    # the fixture names two reference systems, both as an EPSG URL
    CRS_XPATH = ('.//gmd:referenceSystemInfo'
                 '/gmd:MD_ReferenceSystem/gmd:referenceSystemIdentifier'
                 '/gmd:RS_Identifier/gmd:code/gco:CharacterString')

    def _record_with_reference_systems(self, *texts):
        """The dataset fixture with its reference system strings replaced.

        A None text empties the element, which is the shape of the issue: lxml
        answers None for the character content of <gco:CharacterString/>.
        """
        root = etree.fromstring(self.XML.read_bytes())
        elements = root.findall(self.CRS_XPATH, self.NAMESPACES)
        self.assertEqual(len(elements), len(texts),
                         "the fixture must carry one element per given text")
        for element, text in zip(elements, texts):
            element.text = text
        mapper = MDMetadataXmlMapper.from_xml(root)[0]
        mapper.xml_to_django()
        PersistenceHandler(mapper).persist_all()
        return DatasetMetadataRecord.objects.get(
            file_identifier='de.dwd.geoserver.fach.RBSN_FF')

    def test_an_empty_reference_system_element_costs_the_record_nothing(self):
        # both elements carry no character content: lxml gives None for their text
        record = self._record_with_reference_systems(None, None)
        self.assertEqual(record.title, EXPECTED_DATASET_DATA["title"])
        self.assertFalse(
            record.reference_systems.exists(),
            "an unusable reference system must not produce a row")
        # the rest of the record is untouched
        self.assertTrue(record.keywords.exists())
        self.assertTrue(record.languages.exists())
        self.assertIsNotNone(record.bounding_geometry)

    def test_an_empty_reference_system_element_keeps_the_others(self):
        record = self._record_with_reference_systems(
            None, 'http://www.opengis.net/def/crs/EPSG/0/4326')
        self.assertCountEqual(
            record.reference_systems.values_list('code', flat=True), ['4326'])

    def test_valid_reference_systems_still_map_after_the_fix(self):
        record = self._record_with_reference_systems(
            'http://www.opengis.net/def/crs/EPSG/0/4258',
            'http://www.opengis.net/def/crs/EPSG/0/4326')
        self.assertCountEqual(
            record.reference_systems.values_list('code', flat=True),
            EXPECTED_DATASET_DATA["reference_systems"])


class ParseReferenceSystemNodeTest(TestCase):
    """The parser's contract on the two node types its signature names (#1074).

    An element without character content answers like the empty case of the
    character branch: a reference system without a code is a missing value, so
    the answer is None and the mapping of the record continues. Everything the
    parser could read before keeps its answer.
    """

    def _element(self, text):
        """A character string element carrying `text` as its character content;
        None builds the empty <gco:CharacterString/> of the issue."""
        ns = 'xmlns:gco="http://www.isotc211.org/2005/gco"'
        if text is None:
            xml = f'<gco:CharacterString {ns}/>'
        else:
            xml = f'<gco:CharacterString {ns}>{text}</gco:CharacterString>'
        return etree.fromstring(xml.encode())

    def test_element_without_character_content_answers_none(self):
        for text in (None, "", "  \n "):
            with self.subTest(text=text):
                self.assertIsNone(
                    parse_reference_system(None, self._element(text)))

    def test_empty_text_node_answers_none(self):
        element = self._element("http://www.opengis.net/def/crs/EPSG/0/4258")
        element.text = ""
        text_node = element.xpath("./text()")[0]
        self.assertIsNone(parse_reference_system(None, text_node))

    def test_readable_crs_answers_as_before(self):
        for crs, code in (
            ("http://www.opengis.net/def/crs/EPSG/0/4258", "4258"),
            ("urn:ogc:def:crs:EPSG::4326", "4326"),
            ("EPSG:31467", "31467"),
        ):
            with self.subTest(crs=crs):
                instance = parse_reference_system(None, self._element(crs))
                self.assertEqual(instance.code, code)
                self.assertEqual(
                    instance.prefix, ReferenceSystemPrefixChoices.EPSG)


class MetadataRecordRepublishRegressionTest(TestCase):
    """Tests the persistence of a record which the catalogue republished.

    A record which is harvested again with a newer date stamp is updated in
    place by get_or_create_metadatarecord. That update copied every field of
    the parsed but unsaved instance onto the fetched row - including the
    freshly generated primary key of the instance - and turned the update into
    an insert which collided with the record itself (#811).
    """

    XML = Path(Path.joinpath(
        Path(__file__).parent.resolve(),
        '../../test_data/iso_metadata/dataset.xml'))

    def _persist_dataset(self):
        mapper = MDMetadataXmlMapper.from_xml(self.XML)[0]
        mapper.xml_to_django()
        handler = PersistenceHandler(mapper)
        handler.persist_all()

    def test_a_republished_record_is_updated_in_place(self):
        self._persist_dataset()
        record = DatasetMetadataRecord.objects.get()
        republished = record.date_stamp

        # the catalogue republishes the record: what the next harvest parses
        # carries a newer date stamp than the row which is stored
        DatasetMetadataRecord.objects.filter(pk=record.pk).update(
            date_stamp=republished - timedelta(days=1))

        self._persist_dataset()

        self.assertEqual(1, DatasetMetadataRecord.objects.count())
        record.refresh_from_db()
        self.assertEqual(republished, record.date_stamp)
