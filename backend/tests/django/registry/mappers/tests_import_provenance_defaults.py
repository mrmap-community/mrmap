"""The provenance defaults of an import land on the written rows (mrmap#976).

`md_metadata_file_to_db` hands the persistence handler the provenance of a
run - `origin` and `origin_url` per record type - so that a harvested record
answers where it came from and which catalogue it came from. That handover was
thrown away twice over, for every record type: the handler read its defaults by
model class name while the harvest keys them `"dataset"`, `"service"` and
`"application"`, and the write values of a record `setdefault`-ed the defaults
onto the field values of the parsed instance, which already name every column -
the empty ones as `None` (#858 wrote that path, #975 surfaced it).

This module is the contract of the fix, at the level the application mapping
tests of #826 sit on: the mapper parses a sampled document, the
PersistenceHandler writes it with the defaults an import passes, and the stored
row answers them - for all three record types, for a new record and for a
republished one, and for both ways of keying the defaults. What the document
itself maps onto is never overwritten by a default.
"""

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.db.models import F
from django.test import TestCase, override_settings
from registry import models
from registry.enums.metadata import MetadataOriginEnum
from registry.mappers.configs import XPATH_MAP
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.persistence.custom import METADATA_RECORD_TYPE_KEYS
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord,
                                      MetadataContact,
                                      ServiceMetadataRecord)
from tests.django.test_data.iso_metadata.expected_dataset_data import \
    EXPECTED_DATA as EXPECTED_DATASET_DATA

ISO_DATA = Path(__file__).parent / '../../test_data/iso_metadata'

# one sampled ISO document per record type; dataset.xml and service.xml are the
# fixtures of the shared mapper tests, gdi-bw-01.xml one of the application
# samples of #825
SAMPLES = {
    "dataset": ("dataset.xml", DatasetMetadataRecord),
    "service": ("service.xml", ServiceMetadataRecord),
    "application": ("gdi-bw-01.xml", ApplicationMetadataRecord),
}

# fake provenance which names this import and nothing else, in the shape
# md_metadata_file_to_db passes it: a catalogue run and the url of the record
CATALOGUE_ORIGIN = MetadataOriginEnum.CATALOGUE.value
CATALOGUE_URL = "https://csw.example.de/oai/GetRecordById"
REPUBLISHED_URL = "https://csw.example.de/oai/GetRecordById.v2"


def provenance(key, url=CATALOGUE_URL):
    """The provenance of a catalogue run, keyed the way `key` names it."""
    return {key: {"origin": CATALOGUE_ORIGIN, "origin_url": url}}


class ProvenanceImportHarness:
    """Imports a sampled document through the persistence handler.

    The same level as the application mapping tests of #826: the mapper parses
    the document and the handler writes it; no harvesting job is involved,
    because the bookkeeping of a run is #827's subject. Only the provenance
    defaults of an import are real - they are what these tests follow through
    to the stored row.
    """

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

    def import_document(self, name, defaults):
        """Parses one sampled document and persists it with these defaults."""
        mapper = MDMetadataXmlMapper.from_xml(ISO_DATA / name)[0]
        mapper.xml_to_django()
        handler = PersistenceHandler(mapper, defaults=defaults)
        handler.persist_all()


class HarvestProvenanceReachesTheRowTest(ProvenanceImportHarness, TestCase):
    """The provenance an import passes is stored on every record it writes."""

    def test_harvest_keyed_provenance_lands_on_the_written_row(self):
        """A run keys its provenance by record type; the row answers it.

        This is the handover of `md_metadata_file_to_db` unchanged: the dict is
        keyed `"dataset"`, `"service"` and `"application"`.
        """
        for type_key, (document, model) in SAMPLES.items():
            with self.subTest(record=type_key):
                self.import_document(document, provenance(type_key))
                record = model.objects.get()
                self.assertEqual(record.origin, CATALOGUE_ORIGIN)
                self.assertEqual(record.origin_url, CATALOGUE_URL)

    def test_class_name_keyed_provenance_lands_on_the_written_row(self):
        """A caller naming the model class gets the same answer (#976)."""
        for type_key, (document, model) in SAMPLES.items():
            with self.subTest(record=model.__name__):
                self.import_document(
                    document, provenance(model.__name__))
                record = model.objects.get()
                self.assertEqual(record.origin, CATALOGUE_ORIGIN)
                self.assertEqual(record.origin_url, CATALOGUE_URL)

    def test_provenance_lands_on_a_republished_record_too(self):
        """The update of a republished record carries the provenance as well.

        The defect lost the defaults on both branches of the import; catching
        only the insert would leave the updated row answering the old url.
        """
        document, model = SAMPLES["dataset"]
        self.import_document(document, provenance("dataset"))
        record = model.objects.get()
        self.assertEqual(record.origin_url, CATALOGUE_URL)

        # the catalogue republishes: the stored row is older than the document
        # the next harvest imports
        model.objects.filter(pk=record.pk).update(
            date_stamp=F('date_stamp') - timedelta(days=1))
        self.import_document(
            document, provenance("dataset", url=REPUBLISHED_URL))

        record.refresh_from_db()
        self.assertEqual(record.origin, CATALOGUE_ORIGIN)
        self.assertEqual(record.origin_url, REPUBLISHED_URL)

    def test_a_default_never_overwrites_what_the_document_mapped(self):
        """A default fills the empty columns of the document, nothing else."""
        document, model = SAMPLES["dataset"]
        defaults = provenance("dataset")
        defaults["dataset"]["title"] = "PROVENANCE DEFAULT"
        self.import_document(document, defaults)

        record = model.objects.get()
        self.assertEqual(record.title, EXPECTED_DATASET_DATA["title"])
        self.assertEqual(record.origin, CATALOGUE_ORIGIN)


class DefaultsKeyingTest(TestCase):
    """Both ways of keying the defaults resolve, for all three record types."""

    def test_defaults_keyed_by_record_type_name_resolve(self):
        for type_key, (_, model) in SAMPLES.items():
            with self.subTest(record=type_key):
                handler = PersistenceHandler(
                    None, defaults=provenance(type_key))
                self.assertEqual(handler.defaults_of(model),
                                 provenance(type_key)[type_key])

    def test_defaults_keyed_by_model_class_name_resolve(self):
        for type_key, (_, model) in SAMPLES.items():
            with self.subTest(record=model.__name__):
                handler = PersistenceHandler(
                    None, defaults=provenance(model.__name__))
                self.assertEqual(
                    handler.defaults_of(model),
                    provenance(model.__name__)[model.__name__])

    def test_the_model_class_name_wins_where_both_keys_are_given(self):
        handler = PersistenceHandler(None, defaults={
            "dataset": {"origin": CATALOGUE_ORIGIN},
            "DatasetMetadataRecord": {"origin":
                                      MetadataOriginEnum.UPLOAD.value},
        })
        self.assertEqual(handler.defaults_of(DatasetMetadataRecord),
                         {"origin": MetadataOriginEnum.UPLOAD.value})

    def test_a_model_without_defaults_answers_nothing(self):
        handler = PersistenceHandler(
            None, defaults=provenance("dataset"))
        self.assertEqual(handler.defaults_of(MetadataContact), {})

    def test_the_record_type_keys_name_an_iso_mapping_and_its_model(self):
        """Adding a record type means the config, the model and this keying.

        The keys of `METADATA_RECORD_TYPE_KEYS` are the record type names of
        the ISO mapping configs and the model class names the mapper parses
        onto; one of the three drifting is what this guard catches.
        """
        by_name = {model.__name__: (type_key, model)
                   for type_key, (_, model) in SAMPLES.items()}
        self.assertEqual(set(METADATA_RECORD_TYPE_KEYS), set(by_name))
        for class_name, type_key in METADATA_RECORD_TYPE_KEYS.items():
            with self.subTest(record=class_name):
                key_of_model, model = by_name[class_name]
                self.assertEqual(key_of_model, type_key)
                self.assertIn(("ISO", type_key), XPATH_MAP)
                self.assertIs(getattr(models.metadata, class_name), model)
