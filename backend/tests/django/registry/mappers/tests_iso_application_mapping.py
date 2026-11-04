"""The ("ISO","application") mapping of real application metadata records (issue #826).

The ten documents in `tests/django/test_data/iso_metadata/` are live
`hierarchyLevel=application` records sampled from four CSWs for #825 (sources:
`SOURCES.md` in that directory). Every one of them carries its identification as
`gmd:MD_DataIdentification` -- application records are shaped like dataset records,
not like service records -- so the mapping config for `("ISO", "application")`
mirrors the dataset config with a generic identification content (`*`) and maps
onto `ApplicationMetadataRecord`. These tests are the contract of that decision:

* every sample maps onto an `ApplicationMetadataRecord` and lands in the database
  with title, abstract, file identifier, date stamp, keywords, extent, contacts,
  categories, languages, time extents, constraints and code populated from the
  real XPaths of the document,
* the fields the spike found empty in 0/10 application records (fees, use
  limitation, licence, license_source_note) stay empty, and lineage has no field
  to land on at all -- the document itself is kept in `xml_backup_file`,
* `charset` is matched without the dead wis.wmo.int codeList predicate of the
  dataset config: every sample names `utf8` with a *different* codeList URI and
  all of them populate the field,
* the denormalized `keywords_list` and the `search_vector` of a record are
  maintained for the application table by the database, like for the two existing
  record types (the trigger migration of #826),
* the config mirrors the dataset config where it is intended to (drift guard).

Documented edge case: `geocat-01.xml` carries Swiss `CHE_MD_Metadata` roots and is
rejected by the shared `MD_Metadata` detection of the mapper -- out of scope of
#826 (follow-up of #825), and this module pins that it stays a clean error.
"""

from datetime import date, datetime
from datetime import timezone as datetime_timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings
from django.utils import timezone
from registry.enums.iso import (CategoryChoices, LanguageChoices,
                                MetadataCharsetChoices,
                                UpdateFrequencyChoices)
from registry.expressions.search import client_search_query
from registry.mappers.configs import XPATH_MAP
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord,
                                      ServiceMetadataRecord)

ISO_DATA = Path(__file__).parent / '../../test_data/iso_metadata'

# the identification content element of the dataset config which the application
# config replaces with the generic "*"
DATASET_IDENTIFICATION = "gmd:MD_DataIdentification"

UTC = datetime_timezone.utc

# per-sample expectations, taken from the documents themselves; the per-field
# XPath evidence is the spike analysis referenced in SOURCES.md. Notable
# pipeline-wide behaviors which the expectations record:
#
# * a multi-valued contact field is answered by the LAST element the base_xpath
#   names, and the bbox parser is fed the FIRST geographicElement -- both are the
#   existing behavior of the mapper for dataset records, the application config
#   deliberately behaves the same,
# * the codeListValue "asNeeded" is no label of UpdateFrequencyChoices ("as
#   needed" is), so those records answer no update frequency -- like a dataset
#   record with the same codeListValue does today.
EXPECTED = {
    "gdi-bw-01.xml": {
        "file_identifier": "270C4127-5EE3-477D-A3E4-2834649CD57C",
        "title": "ELWIS - www.elwis.de - Website",
        "abstract": "Elektronisches Wasserstraßen-Informationssystem der WSV",
        "date_stamp": date(2026, 3, 30),
        "keywords": [
            "Binnengewässer", "wsv_topic_code:application", "Pegelauswahl",
            "Karte", "Leitfaden", "Schifffahrtsrecht", "Verkehrslenkung",
            "Schweiz", "Mittelrhein", "Niederrhein", "Verkehr",
            "Binnenschifffahrt",
        ],
        "categories": [],
        "languages": [LanguageChoices.GER],
        "application_contact": "GDWS - Generaldirektion Wasserstraßen und Schifffahrt",
        "metadata_contact": "ITZBund - Informationstechnikzentrum Bund, Poststelle",
        "extent": (6.098034, 47.23942, 15.578555, 55.054344),
        "time_extents": [],
        "access_constraints": None,
        "update_frequency_code": None,
        "equivalent_scale": None,
        "code": "", "code_space": "",
        "reference_systems": [],
    },
    "gdi-bw-02.xml": {
        "file_identifier": "5E243836-9359-40AD-B887-E0A526F3979E",
        "title": "PEGELONLINE, gewässerkundliches Informationssystem der WSV",
        "abstract": "PEGELONLINE (www.pegelonline.wsv.de)",
        "date_stamp": date(2026, 8, 20),
        "keywords": ["mobilithek_category_WATERROADS_AND_WATER", "opendata",
                     "ENVI", "TRAN"],
        "categories": [],
        "languages": [LanguageChoices.GER],
        # three pointOfContacts, the last one names GDWS
        "application_contact": "GDWS - Generaldirektion Wasserstraßen und Schifffahrt",
        "metadata_contact": "ITZBund - Informationstechnikzentrum Bund, Poststelle",
        "extent": (6.098, 47.239, 15.579, 55.054),
        "time_extents": [],
        "access_constraints": None,
        "update_frequency_code": UpdateFrequencyChoices.DAILY,
        "equivalent_scale": None,
        "code": "", "code_space": "",
        "reference_systems": [],
    },
    # the reference fixture of #826: populates nearly everything in one record
    "gdi-bw-04.xml": {
        "file_identifier": "78538593-0e19-a5b7-c64a-756898eac073",
        "title": "Geoportal Stadt Schwäbisch Hall",
        "abstract": "Portal zur Darstellung von kommunalen Geodaten der Stadt",
        "date_stamp": date(2023, 11, 14),
        "keywords": [
            "Geodäsie", "Geobasisdaten", "Raumordnung",
            "Tourismus und Freizeit", "Straße", "Kartographie", "Topographie",
            "Kataster", "Höhe", "kommunale Geodaten", "Stadtkarte",
            "Administrative units", "Addresses", "Cadastral parcels",
            "Protected sites", "Orthoimagery", "Statistical units",
            "Buildings", "Bodenrichtwert", "Flächennutzungsplan",
            "Bebauungsplan", "Wahlbezirk", "Wahllokal", "Schulbezirk",
            "Gedenkorte", "Häuserlexikon", "Bauplatz", "Statistik",
            "Historische Luftbilder", "ÖPNV",
        ],
        "categories": [
            CategoryChoices.BOUNDARIES, CategoryChoices.ELEVATION,
            CategoryChoices.EVNVIRONMENT,
            CategoryChoices.IMAGERYBASEMAPSEARTHCOVER,
            CategoryChoices.LOCATION, CategoryChoices.PLANNINGCADASTRE,
            CategoryChoices.SOCIETY,
        ],
        "languages": [LanguageChoices.GER],
        "application_contact": "ibb DV-Systems GmbH",
        "metadata_contact": "Stadt Schwäbisch Hall",
        "extent": (9.54, 49.02, 9.92, 49.18),
        "time_extents": [],
        "access_constraints": None,
        "update_frequency_code": None,
        "equivalent_scale": None,
        # the MD_Identifier of the citation, kept verbatim and split like the
        # dataset config splits it
        "code": "schwaebischhall",
        "code_space": "https://www.gisserver.de/",
        "reference_systems": [],
    },
    "gdi-de-01.xml": {
        "file_identifier": "17517355-a52a-4823-add7-1d5c99536eeb",
        "title": "Kreis Herford: Alltagsradwegenetz",
        "abstract": "Der Kreis Herford hat mit Hilfe des Planungsbüros",
        "date_stamp": date(2024, 5, 7),
        "keywords": [
            "Fahrrad", "Fahrradweg", "Mobilität", "Radweg", "Radwege",
            "Radwegenetz", "Alltag", "Alltagsradwegenetz", "Fahrradstraße",
            "Pendler", "Bike", "Bicycle", "Mobilitätsmanagement", "Startseite",
            "KreisHerford", "Herford", "Bünde", "Hiddenhausen", "Löhne",
            "Kirchlengern", "Vlotho", "Spenge", "Enger", "Rödinghausen",
        ],
        "categories": [CategoryChoices.TRANSPORTATION],
        "languages": [LanguageChoices.GER],
        "application_contact": "Stabsbereich Kreisentwicklung und Klimaschutz",
        "metadata_contact": "Kataster und Vermessung",
        "extent": (8.396, 52.043, 8.932, 52.28),
        "time_extents": [],
        "access_constraints": None,
        "update_frequency_code": None,
        "equivalent_scale": None,
        "code": "", "code_space": "",
        # this record names its reference system as a gmx:Anchor instead of the
        # gco:CharacterString the (dataset) path reads -- parity with datasets,
        # which lose the anchor variant the same way
        "reference_systems": [],
    },
    "gdi-de-03.xml": {
        "file_identifier": "18923033-6CCD-11D3-98D2-0060086FDABA",
        "title": "Daten genehmigungsbedürfiger Anlagen (StALU WM Schwerin)",
        "abstract": "Daten der nach dem Bundes- Immissionsschutzgesetz",
        "date_stamp": date(2025, 1, 28),
        "keywords": [
            "Produktions- und Industrieanlagen",
            "Bundesimmissionsschutzgesetz (BImSchG)",
            "4. Bundesimmissionsschutzverordnung (BImSchV)",
        ],
        "categories": [],
        "languages": [LanguageChoices.GER],
        "application_contact": "Staatliches Amt für Landwirtschaft und Umwelt Westmecklenburg, Dienststelle Schwerin (StALU WM SN)",
        "metadata_contact": "Staatliches Amt für Landwirtschaft und Umwelt Westmecklenburg, Dienststelle Schwerin (StALU WM SN)",
        # five bounding boxes, the first is stored (see module docstring)
        "extent": (10.593673, 53.11003, 11.85377, 53.65325),
        # open-ended period: the empty endPosition answers the begin instant on
        # both sides, like it does for a dataset record with an empty endPosition
        "time_extents": [(datetime(1990, 6, 30, 22, 0, tzinfo=UTC),
                          datetime(1990, 6, 30, 22, 0, tzinfo=UTC))],
        "access_constraints": None,
        "update_frequency_code": None,
        "equivalent_scale": None,
        "code": "", "code_space": "",
        "reference_systems": [],
    },
    "gdi-de-04.xml": {
        "file_identifier": "19c44805-c445-4f4a-8420-e71797bf4088",
        "title": "Kreis Gütersloh: Liegenschaftskarte (nicht amtlich)",
        "abstract": "Mit Hilfe der Anwendung können nicht amtliche Auszüge",
        "date_stamp": date(2019, 1, 21),
        "keywords": ["Kreis Gütersloh", "Liegenschaftskarte", "Kataster"],
        "categories": [CategoryChoices.LOCATION,
                       CategoryChoices.PLANNINGCADASTRE],
        "languages": [LanguageChoices.GER],
        "application_contact": "Kreis Gütersloh",
        "metadata_contact": "Kreis Gütersloh",
        "extent": (8.0011, 51.7042, 8.7325, 52.1564),
        "time_extents": [],
        # seven EMPTY gmd:resourceConstraints and no legal-constraints block
        # with an otherConstraints text: nothing to map, nothing explodes
        "access_constraints": None,
        "update_frequency_code": None,
        "equivalent_scale": None,
        "code": "", "code_space": "",
        "reference_systems": [],
    },
    "gdi-de-05.xml": {
        "file_identifier": "12f10205-53c7-459c-bf6e-40e67ccd0c00",
        "title": "Unfallatlas",
        "abstract": "Im Unfallatlas werden Unfälle mit Personenschaden",
        "date_stamp": date(2024, 8, 13),
        "keywords": [
            "Unfallatlas", "Straßenverkehrsunfälle",
            "Straßenverkehrsunfallstatistik", "Unfall", "Unfälle", "Verkehr",
            "Statistik", "Deutschland", "transport_verkehr",
        ],
        "categories": [CategoryChoices.TRANSPORTATION],
        "languages": [LanguageChoices.GER],
        # two pointOfContacts, the last one names the Bundesamt
        "application_contact": "Statistisches Bundesamt",
        "metadata_contact": "Information und Technik Nordrhein-Westfalen",
        "extent": (5.81, 47.26, 15.77, 54.76),
        "time_extents": [(datetime(2016, 1, 1, tzinfo=UTC),
                          datetime(2016, 1, 1, tzinfo=UTC))],
        "access_constraints": "Dieses Werk ist lizensiert unter der Datenlizenz Deutschland - Namensnennung - Version 2.0 (www.govdata.de/dl-de/by-2-0)",
        "update_frequency_code": UpdateFrequencyChoices.ANNUALLY,
        "equivalent_scale": None,
        "code": "", "code_space": "",
        "reference_systems": [],
    },
    "hessen-01.xml": {
        "file_identifier": "0a7cb996-69d1-69bd-9e64-da089a3bb1e4",
        "title": "Statistik räumlich sehen - das CCG",
        "abstract": "Statistik räumlich sehen, ist unsere Mission.",
        "date_stamp": date(2026, 11, 2),
        # the keyword-registry UUID which Hessen prefixes every record with is
        # kept like any other keyword
        "keywords": [
            "1c349fea-924b-488f-b6a2-e896f40ac897", "CCG", "Digital",
            "Fernerkundung", "GDI", "Geodateninfrastruktur", "Hessen",
            "Hessisches Statistisches Landesamt", "Statistik",
        ],
        "categories": [CategoryChoices.GEOSCIENTIFICINFORMATION],
        "languages": [LanguageChoices.GER],
        "application_contact": "HSL",
        "metadata_contact": "HSL",
        "extent": (7.695788, 49.379589, 10.238454, 51.658643),
        "time_extents": [(datetime(2021, 1, 1, tzinfo=UTC),
                          datetime(2021, 12, 31, tzinfo=UTC))],
        "access_constraints": "keine Beschränkung",
        "update_frequency_code": None,
        "equivalent_scale": 0.0,
        # Hessen's codes are URLs containing /dataset/ even on application
        # records -- kept verbatim, split like the dataset path splits them
        "code": "0a7cb996-69d1-69bd-9e64-da089a3bb1e4",
        "code_space": "https://statistik-hessen.de/registry/spatial/dataset/",
        "reference_systems": ["25832"],
    },
    "hessen-03.xml": {
        "file_identifier": "1a83899e-8bad-5be4-1ec3-7486a9ec3d35",
        "title": "Geoportal Südhessen",
        "abstract": "Über das Geoportal Südhessen erhalten Sie Zugang",
        "date_stamp": date(2026, 11, 2),
        "keywords": [
            "1c349fea-924b-488f-b6a2-e896f40ac897", "Bauleitplan",
            "Bauleitplanung", "Bebauunsplan", "Bergstraße",
            "Biotop- und Nutzungskartierung", "Darmstadt-Dieburg", "Feuerwehr",
            "Feuerwehrstandorte und Einsatzbereiche", "FrankfurtRheinMain",
            "GDI-Südhessen", "Geodaten", "Geodateninfrastruktur", "Geoportal",
            "Geoportal Südhessen", "Groß-Gerau", "Hochtaunuskreis",
            "Industrieflächen", "KBRP", "Kita",
            "Kommunale Boden- und Raumplanung", "Limburg-Weilburg",
            "Main-Kinzig-Kreis", "Main-Taunus-Kreis", "Odenwaldkreis",
            "Open-Data", "RegFNP", "Regionaler Flächennutzungsplan",
            "Regionalverband", "Rettungswachen", "Rettungswachen und -bezirke",
            "Rheingau-Taunus-Kreis", "Schulstandorte und -bezirke",
            "Wetteraukreis", "XPlanung",
        ],
        # the literal junk text "no category defined till now!" is no valid
        # MD_TopicCategoryCode: the answer is None, the rest of the record
        # imports
        "categories": [],
        "languages": [LanguageChoices.GER],
        "application_contact": "GDI-SÜDHESSEN",
        "metadata_contact": "GDI-SÜDHESSEN",
        "extent": (7.7724673, 49.3952723, 9.7488228, 50.5996859),
        "time_extents": [(datetime(2022, 7, 24, tzinfo=UTC),
                          datetime(2026, 11, 2, tzinfo=UTC))],
        "access_constraints": "keine Beschränkungen",
        "update_frequency_code": UpdateFrequencyChoices.CONTINUAL,
        "equivalent_scale": 0.0,
        "code": "1a83899e-8bad-5be4-1ec3-7486a9ec3d35",
        "code_space": "https://gdi-suedhessen.de/registry/spatial/dataset/",
        "reference_systems": ["4326"],
    },
}

# geocat-01.xml is not in EXPECTED: CHE_MD_Metadata roots, see
# CheMetadataRejectionTest below.
SAMPLES = sorted(EXPECTED)


class ApplicationRecordImportHarness:
    """Imports one application sample the way the persistence layer does.

    The document is parsed by the mapper and written by the PersistenceHandler.
    The provenance an import adds -- ``origin``, ``origin_url``, the
    ``HarvestedMetadataRelation`` and the per-type counts -- is #827's subject,
    so the handler is handed no defaults: what these tests answer is what the
    document maps onto, and nothing a harvest would add on top of it.
    """

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

    def parse(self, name):
        """The single parsed instance of one sample document."""
        mappers = MDMetadataXmlMapper.from_xml(ISO_DATA / name)
        self.assertEqual(len(mappers), 1,
                         f"{name}: expected exactly one MD_Metadata record")
        mapper = mappers[0]
        self.assertEqual(
            MDMetadataXmlMapper._detect_hierarchy_level(mapper.xml_root),
            "application", f"{name}: detected hierarchyLevel")
        instances = mapper.xml_to_django()
        self.assertEqual(len(instances), 1,
                         f"{name}: expected one mapped instance")
        self.assertIsInstance(instances[0], ApplicationMetadataRecord,
                              f"{name}: mapped onto the wrong model")
        return mapper

    def import_sample(self, name):
        """Parses one sample and persists it; answers the stored record."""
        mapper = self.parse(name)
        instance = mapper.data[0]
        handler = PersistenceHandler(mapper)
        handler.persist_all()
        record = ApplicationMetadataRecord.objects.get(
            file_identifier=instance.file_identifier)
        record.xml_backup_file.open("rb")
        self.addCleanup(record.xml_backup_file.close)
        return record


class ApplicationRecordMappingTest(ApplicationRecordImportHarness, TestCase):
    """Every sampled application record maps onto ApplicationMetadataRecord."""

    def test_every_sample_lands_as_an_application_metadata_record(self):
        for name in SAMPLES:
            with self.subTest(sample=name):
                expected = EXPECTED[name]
                record = self.import_sample(name)

                self.assertEqual(record.file_identifier,
                                 expected["file_identifier"])
                self.assertEqual(record.title, expected["title"])
                self.assertIn(expected["abstract"], record.abstract)
                # date_stamp is parsed into the current timezone (#825 samples
                # all carry a plain date)
                self.assertEqual(
                    timezone.localtime(record.date_stamp).date(),
                    expected["date_stamp"])
                self.assertEqual(
                    record.charset, MetadataCharsetChoices.UTF8.value,
                    f"{name}: the charset matched without the dead wmo "
                    "codeList predicate")

                self.assertCountEqual(
                    record.keywords.values_list("keyword", flat=True),
                    expected["keywords"], f"{name}: keywords")
                self.assertCountEqual(
                    record.categories.values_list("value", flat=True),
                    [c.value for c in expected["categories"]],
                    f"{name}: categories")
                self.assertCountEqual(
                    record.languages.values_list("value", flat=True),
                    [language.value for language in expected["languages"]],
                    f"{name}: languages")
                self.assertCountEqual(
                    record.reference_systems.values_list("code", flat=True),
                    expected["reference_systems"], f"{name}: reference systems")

                self.assertEqual(record.application_contact.name,
                                 expected["application_contact"],
                                 f"{name}: application_contact")
                self.assertEqual(record.metadata_contact.name,
                                 expected["metadata_contact"],
                                 f"{name}: metadata_contact")

                self.assertIsNotNone(record.bounding_geometry,
                                     f"{name}: no bounding geometry")
                self.assertEqual(
                    tuple(round(v, 6) for v in record.bounding_geometry.extent),
                    tuple(round(v, 6) for v in expected["extent"]),
                    f"{name}: extent")

                self.assertEqual(
                    [(e.begin, e.end) for e in record.time_extents.all()],
                    expected["time_extents"], f"{name}: time extents")

                self.assertEqual(record.access_constraints,
                                 expected["access_constraints"],
                                 f"{name}: access_constraints")
                self.assertEqual(
                    record.update_frequency_code,
                    expected["update_frequency_code"].value
                    if expected["update_frequency_code"] else None,
                    f"{name}: update_frequency_code")
                self.assertEqual(record.equivalent_scale,
                                 expected["equivalent_scale"],
                                 f"{name}: equivalent_scale")
                self.assertEqual(record.code, expected["code"],
                                 f"{name}: code")
                self.assertEqual(record.code_space, expected["code_space"],
                                 f"{name}: code_space")

    def test_the_fields_the_spike_found_empty_stay_empty(self):
        """fees / use_limitation / licence / license_source_note: 0/10 in the
        spike -- nothing in the config writes onto them. Lineage (0/10 with
        content) has no field at all; the document stays in xml_backup_file."""
        for name in SAMPLES:
            with self.subTest(sample=name):
                record = self.import_sample(name)
                self.assertFalse(record.fees, f"{name}: fees")
                self.assertFalse(record.use_limitation,
                                 f"{name}: use_limitation")
                self.assertIsNone(record.licence, f"{name}: licence")
                self.assertFalse(record.license_source_note,
                                 f"{name}: license_source_note")
                self.assertFalse(hasattr(record, "lineage_statement"),
                                 f"{name}: lineage field must not exist")

        # the statement-less lineage node of hessen-01 stays in the backup:
        # nothing maps it, the XML is kept verbatim
        record = self.import_sample("hessen-01.xml")
        self.assertIn(b"LI_Lineage", record.xml_backup_file.read())

    def test_a_republished_document_updates_the_record_in_place(self):
        """The application branch of the config selects the same custom
        persistence as the dataset branch, including its file-identifier
        lookup -- importing a document twice is one record."""
        first = self.import_sample("gdi-bw-04.xml")
        second = self.import_sample("gdi-bw-04.xml")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ApplicationMetadataRecord.objects.count(), 1)


class ApplicationRecordDatabaseMaintenanceTest(ApplicationRecordImportHarness, TestCase):
    """The application table participates in the database-maintained search
    columns of a metadata record exactly like the two existing record types:
    the keywords array is kept from the keywords relation and the stored
    generated vector is computed from it (trigger migration of #826)."""

    def test_keywords_are_denormalized_and_the_record_is_findable(self):
        record = self.import_sample("gdi-bw-04.xml")
        expected = EXPECTED["gdi-bw-04.xml"]["keywords"]
        self.assertEqual(sorted(record.keywords_list), sorted(expected))
        self.assertTrue(record.search_vector)

        found = ApplicationMetadataRecord.objects.filter(
            search_vector=client_search_query("Geoportal Schwäbisch Hall"))
        self.assertIn(record.pk, [r.pk for r in found])

        # ... and only through its own table: the other record types are empty
        self.assertFalse(DatasetMetadataRecord.objects.filter(
            search_vector=client_search_query("Geoportal")).exists())
        self.assertFalse(ServiceMetadataRecord.objects.filter(
            search_vector=client_search_query("Geoportal")).exists())

    def test_the_history_of_a_record_tracks_its_writes(self):
        """django-simple-history writes the audit rows of an application
        record, and the diff size column of that table is answered by the
        database like on the existing history tables (migration 0025): NULL
        without a predecessor, one for the save which renamed the title."""
        record = self.import_sample("gdi-bw-04.xml")
        record.title = "renamed by the curator"
        record.save()

        rows = list(record.change_log.order_by("history_date"))
        self.assertEqual(len(rows), 2)
        self.assertEqual([row.delta_size for row in rows], [None, 1])


class ApplicationConfigDriftGuardTest(TestCase):
    """The ("ISO","application") config mirrors the dataset config where the
    #825 decision says it must, and the intended differences stay exactly the
    decided ones:

    * the identification content element is the generic ``*`` instead of
      ``gmd:MD_DataIdentification``,
    * the contact field is named ``application_contact``,
    * ``charset`` is matched without the wis.wmo.int codeList predicate.
    """

    def config(self, record_type):
        return XPATH_MAP[("ISO", record_type)]

    def branch(self, record_type):
        return self.config(record_type)[record_type]

    def test_the_application_branch_is_the_dataset_branch_with_a_generic_content(self):
        dataset_config = self.config("dataset")
        application_config = self.config("application")

        # the protocol part of the config: same namespaces, same schema, no
        # pre-save hook of its own
        self.assertEqual(application_config["_namespaces"],
                         dataset_config["_namespaces"])
        self.assertEqual(application_config["_schema"],
                         dataset_config["_schema"])
        self.assertEqual(application_config["_pre_save"],
                         dataset_config["_pre_save"])

        dataset = dataset_config["dataset"]
        application = application_config["application"]

        self.assertEqual(application["_model"],
                         "registry.ApplicationMetadataRecord")
        self.assertEqual(application["_base_xpath"], dataset["_base_xpath"])
        self.assertEqual(application["_create_mode"], dataset["_create_mode"])

        # exactly the dataset's fields, with dataset_contact renamed to
        # application_contact; fees/use_limitation/licence/lineage are not in
        # either config and nothing new was added (#826 decision: no url-style
        # field for distribution links)
        self.assertEqual(
            set(dataset["fields"]) - {"dataset_contact"} | {"application_contact"},
            set(application["fields"]))

        for field, dataset_spec in dataset["fields"].items():
            field_in_application = (
                "application_contact" if field == "dataset_contact" else field)
            if field == "charset":
                continue  # the decided deviation, asserted separately below
            with self.subTest(field=field_in_application):
                self.mirror(
                    field_in_application,
                    dataset_spec,
                    application["fields"][field_in_application])

    def mirror(self, where, dataset_value, application_value):
        """The application spec with the generic ``*`` identification equals
        the dataset spec with the hard-coded one."""
        if isinstance(dataset_value, str):
            self.assertEqual(
                application_value,
                dataset_value.replace(DATASET_IDENTIFICATION, "*"),
                f"{where}: drifted from the dataset config")
        elif isinstance(dataset_value, tuple):
            self.assertEqual(len(dataset_value), len(application_value or ()))
            for index, entry in enumerate(dataset_value):
                self.mirror(f"{where}[{index}]", entry, application_value[index])
        elif isinstance(dataset_value, dict):
            self.assertIsInstance(application_value, dict, where)
            self.assertEqual(set(dataset_value), set(application_value), where)
            for key, entry in dataset_value.items():
                self.mirror(f"{where}.{key}", entry, application_value[key])
        else:
            self.assertEqual(application_value, dataset_value, where)

    def test_the_charset_deviation_is_the_decided_one(self):
        """Every sampled application record (and many dataset records!) names a
        codeList URI other than the wis.wmo.int one the dataset predicate
        pins; the application config matches the codeListValue alone."""
        charset = self.branch("application")["fields"]["charset"]
        self.assertEqual(
            charset["_inputs"],
            ("./gmd:characterSet/gmd:MD_CharacterSetCode/@codeListValue",))
        self.assertEqual(
            charset["_parser"],
            "registry.mappers.parsers.value.charset_to_enum")
        # the dataset config is untouched by this story: its dead predicate
        # stays until it is decided for the existing types as well
        self.assertIn(
            "wis.wmo.int",
            self.branch("dataset")["fields"]["charset"]["_inputs"][0])


class ApplicationRecordShapeTest(TestCase):
    """The model carries exactly the dataset-shaped fields the decision named
    and no distribution-link field."""

    def test_the_record_adds_exactly_contact_frequency_and_categories(self):
        own = ({f.name for f in ApplicationMetadataRecord._meta.local_fields}
               | {f.name for f in ApplicationMetadataRecord._meta.local_many_to_many})
        service = ({f.name for f in ServiceMetadataRecord._meta.local_fields}
                   | {f.name for f in ServiceMetadataRecord._meta.local_many_to_many})
        self.assertEqual(own - service,
                         {"application_contact", "update_frequency_code",
                          "categories"})

    def test_no_field_carries_a_distribution_link(self):
        names = {f.name for f in ApplicationMetadataRecord._meta.get_fields()}
        for forbidden in ("url", "reference_url", "distribution_url",
                          "online_resource", "lineage_statement"):
            self.assertNotIn(forbidden, names)
        # the service records' own reference_url equivalent: only the known
        # origin/xml fields of MetadataRecord are present
        self.assertIn("origin_url", names)
        self.assertIn("xml_backup_file", names)


class CheMetadataRejectionTest(TestCase):
    """geocat.ch serves ``gmd:CHE_MD_Metadata`` roots. Widening the shared
    ``MD_Metadata`` detection of the mapper touches datasets and services and
    is an explicit follow-up of #825 -- this pins that such a document stays a
    clean, named error instead of a crash or a silently dropped file."""

    def test_the_chemdm_sample_is_rejected_by_name(self):
        with self.assertRaises(ValueError) as context:
            MDMetadataXmlMapper.from_xml(ISO_DATA / "geocat-01.xml")
        self.assertIn("No MD_Metadata elements found", str(context.exception))
        self.assertFalse(ApplicationMetadataRecord.objects.exists())
