"""The bookkeeping which closes one collected reference (#1261).

One reference of the collection is one ``RemoteMetadata`` row: a link found
in the capabilities document, the document it fetches and - if the document
identifies a record - the record and the relation which couples it to the
described element. Three answers of that path were open and are pinned here:

*the answer of a reference which produced no record:*
    A document without a resolvable ``gmd:fileIdentifier`` maps to no record
    and ``create_metadata_instance`` answers None (measured: the parsed
    instance keeps re-evaluating the uuid default of the column, so no
    lookup ever agrees on the key). The task used to answer ``"id": "None"``
    and a self link to the path segment "None" - a payload which reads like a
    created record. It now answers no data and a machine-readable outcome,
    counts the step and leaves a warning naming the reference on the process.
    (The stray record row which the mapping still persists in that case is
    identity of the plan - the subject of #1263, not of this answer.)

*the duplicate question, measured on this checkout:*
    Re-collecting one reference - same link, same described element - neither
    duplicates the record (the custom persistence identifies records by their
    file identifier, see ``get_or_create_metadatarecord``) nor duplicates the
    relation (the ``add_metadata_relation`` get_or_create is keyed on the
    filled columns). A second relation row for one identifier arises only
    when the record instance a link resolves to has changed - and the
    collection removes that stale relation as it asserts the new one, runtime
    bookkeeping instead of a deduplication migration, which fits the
    no-migration posture of the epic's decision D5.

*the mapping of a coupling:*
    The ``if/elif`` chains which matched the described object by class name
    defaulted to silence: a class outside the chain wrote a relation row with
    one object column missing, which no screen can render. The mapping is
    explicit now and a class without a column of its own fails loudly.
"""

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from celery.app.trace import build_tracer
from django.apps import apps
from django.test import TestCase, TransactionTestCase, override_settings
from notify.enums import LogTypeEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from registry.enums.metadata import (CollectionStepOutcome,
                                     MetadataOriginEnum)
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord,
                                      FeatureTypeRemoteMetadata,
                                      LayerRemoteMetadata, MetadataRelation,
                                      RemoteMetadata, ServiceMetadataRecord)
from registry.models.service import (FeatureType, Layer, WebFeatureService,
                                     WebMapService)
from registry.tasks.service import fetch_remote_metadata_xml
from rest_framework.reverse import reverse as drf_reverse
from tests.django.utils import WorkerRunMixin

ISO_DATA = Path(__file__).parent / '../../test_data/iso_metadata'
DATASET = (ISO_DATA / 'dataset.xml').read_text()
SERVICE = (ISO_DATA / 'service.xml').read_text()

# the file identifier the dataset sample carries and one the catalogue could
# republish the very same document under
FILE_IDENTIFIER = "de.dwd.geoserver.fach.RBSN_FF"
SECOND_IDENTIFIER = "de.dwd.geoserver.fach.RBSN_SECOND"
LINK = "http://example.gov/md/1"


def document_without_file_identifier():
    """The dataset sample with its gmd:fileIdentifier element removed."""
    stripped = re.sub(
        r'<gmd:fileIdentifier>.*?</gmd:fileIdentifier>', '',
        DATASET, flags=re.S)
    assert 'fileIdentifier' not in stripped
    return stripped


def document_republished():
    """The dataset sample under a different file identifier, same content."""
    republished = DATASET.replace(FILE_IDENTIFIER, SECOND_IDENTIFIER)
    assert SECOND_IDENTIFIER in republished
    return republished


class CollectionHarness:
    """The elements and the document storage which one reference needs."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json"]

    def setUp(self):
        super().setUp()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

        self.wms = WebMapService.objects.first()
        self.layer = Layer.objects.filter(service=self.wms).first()
        self.assertIsNotNone(
            self.layer,
            'the wms fixture must describe a layer to collect for')
        # a second kind of described element, for the cases where one element
        # must stay untouched while another one's coupling is rewritten
        self.wfs = WebFeatureService.objects.first()
        self.feature_type = FeatureType.objects.filter(service=self.wfs).first()
        self.assertIsNotNone(
            self.feature_type,
            'the wfs fixture must describe a feature type')

    def relations(self, record):
        return MetadataRelation.objects.filter(dataset_metadata=record)

    def reference(self, document, link=LINK, describes=None):
        """A fetched reference of the given document, ready to be collected."""
        described = describes if describes is not None else self.layer
        model = (FeatureTypeRemoteMetadata
                 if isinstance(described, FeatureType)
                 else LayerRemoteMetadata)
        return model.objects.create(
            link=link, remote_content=document, describes=described)


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class ReferenceAnswerTests(CollectionHarness, WorkerRunMixin,
                           TransactionTestCase):
    """What the task which collects one reference answers, and what it reports.

    The task is answered through the tracer a worker pays (`WorkerRunMixin`),
    because the reports into the process run in celery's signal handlers; the
    remote fetch is patched - no catalogue is asked of here, the documents
    come from the test data. A `TransactionTestCase` as the registration
    polling tests are: the worker's own handlers close the database
    connection around the task, which a test transaction cannot survive.
    """

    def answer_shared(self, task, task_kwargs):
        """Answer one of the project's real tasks the way a worker would."""
        old_backend = task.__dict__.get("_backend")
        task._backend = self.app.backend
        self.addCleanup(setattr, task, "_backend", old_backend)
        trace = build_tracer(task.name, task, app=self.app)
        return trace(self.task_id, (), task_kwargs, {"id": self.task_id})

    def collect(self, remote_metadata):
        """The reference's task, answered against a process of its own."""
        process = BackgroundProcess.objects.create(
            process_type='registering', phase='collecting metadata records...',
            total_steps=1, done_steps=0)
        with patch.object(
                RemoteMetadata, "fetch_remote_content", return_value=None):
            trace = self.answer_shared(
                fetch_remote_metadata_xml,
                task_kwargs={
                    "remote_metadata_id": remote_metadata.pk,
                    "class_name": "LayerRemoteMetadata",
                    "background_process_pk": str(process.pk),
                })
        return trace.retval, process

    def test_a_document_without_a_file_identifier_answers_no_record(self):
        """No record means no record reference in the answer (#1261).

        The document is the dataset sample with its gmd:fileIdentifier
        removed - the mapping identifies no record in it. The answer carries
        no id, no self link and no "None" standing in for either; it says
        what happened instead, and the process does not end in a state which
        claims a record exists.
        """
        remote_metadata = self.reference(document_without_file_identifier())

        answer, process = self.collect(remote_metadata)

        self.assertIsNone(answer["data"],
                          'a reference which produced no record names none')
        self.assertEqual(
            answer["outcome"],
            CollectionStepOutcome.NO_IDENTIFIABLE_RECORD.value,
            'the answer carries the machine-readable outcome of the step')
        self.assertNotIn(
            "None", json.dumps(answer),
            'no path segment and no id may read like the string "None"')

        # the step is over without a record: the process counts it and the
        # polling client can read why, like every other step which ends
        # without one (#1177)
        process.refresh_from_db()
        self.assertEqual(process.done_steps, 1)
        self.assertEqual(process.status, ProcessStatusEnum.RUNNING)
        self.assertTrue(BackgroundProcessLog.objects.filter(
            background_process=process,
            log_type=LogTypeEnum.WARNING,
            background_process_id=process.pk,
            description__contains=str(remote_metadata.pk),
        ).exists(), 'the reference which left nothing is named in the logs')
        self.assertIsNone(
            process.related_resource_type,
            'the process of this run names no record to a client')

    def test_a_document_with_a_file_identifier_answers_its_record(self):
        """The successful step keeps its answer and says it created a record."""
        remote_metadata = self.reference(DATASET)

        answer, _process = self.collect(remote_metadata)

        record = DatasetMetadataRecord.objects.get(
            file_identifier=FILE_IDENTIFIER)
        self.assertEqual(
            answer,
            {
                "data": {
                    "type": "DatasetMetadataRecord",
                    "id": f"{record.pk}",
                    "links": {"self": drf_reverse(
                        "registry:datasetmetadata-detail", args=[record.pk])},
                },
                "outcome": CollectionStepOutcome.RECORD_CREATED.value,
            })
        self.assertEqual(MetadataRelation.objects.filter(
            dataset_metadata=record, layer=self.layer).count(), 1)


class RelationBookkeepingTests(CollectionHarness, TestCase):
    """The rows which a collection leaves behind - measured, and closed."""

    def test_recollecting_one_reference_duplicates_nothing(self):
        """The measured answer on the duplicate question (#1261).

        The identity rules of #982 identify a dataset record by its file
        identifier, so the second collection of one reference re-asserts the
        relation which is already there: neither the record nor the relation
        row is duplicated. No deduplication migration is needed for this.
        """
        remote_metadata = self.reference(DATASET)

        first = remote_metadata.create_metadata_instance()
        second = remote_metadata.create_metadata_instance()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)
        self.assertEqual(MetadataRelation.objects.count(), 1)

    def test_one_element_with_two_links_keeps_one_relation_per_link(self):
        """A layer may describe several references; each keeps its relation."""
        self.reference(DATASET, link=LINK)
        self.reference(SERVICE, link="http://example.gov/md/2")

        first = LayerRemoteMetadata.objects.get(link=LINK)
        second = LayerRemoteMetadata.objects.get(link="http://example.gov/md/2")
        dataset = first.create_metadata_instance()
        service_record = second.create_metadata_instance()

        self.assertIsInstance(dataset, DatasetMetadataRecord)
        self.assertIsInstance(service_record, ServiceMetadataRecord)
        self.assertEqual(MetadataRelation.objects.count(), 2)
        self.assertTrue(MetadataRelation.objects.filter(
            layer=self.layer, dataset_metadata=dataset,
            service_metadata__isnull=True).exists())
        self.assertTrue(MetadataRelation.objects.filter(
            layer=self.layer, service_metadata=service_record,
            dataset_metadata__isnull=True).exists())

    def test_a_republished_document_replaces_the_stale_relation(self):
        """The "removes the stale ones" half of the re-registration contract.

        When the record which a link resolves to has changed, the element's
        old relation to the superseded instance is taken back as the new one
        is asserted - and only that one: the feature type which describes the
        very same link keeps its coupling to the superseded record (it is a
        different element and its own references decide about it), and
        everything a curator added stays.
        """
        remote_metadata = self.reference(DATASET)
        superseded = remote_metadata.create_metadata_instance()
        self.assertEqual(superseded.file_identifier, FILE_IDENTIFIER)

        # the same link, described by a feature type: a coupling which this
        # collection does not own, and a curator's coupling of the layer
        self.reference(DATASET, link=LINK, describes=self.feature_type)
        superseded.add_metadata_relation(related_object=self.feature_type)
        curated = superseded.add_metadata_relation(
            related_object=self.layer,
            origin=MetadataOriginEnum.EDITOR.value, is_internal=True)

        # the catalogue republished its document under a new file identifier
        republished = self.reference(
            document_republished(), link=LINK)
        replacement = republished.create_metadata_instance()
        self.assertNotEqual(replacement.pk, superseded.pk)

        # the stale coupling of this element to the superseded record is gone
        self.assertFalse(MetadataRelation.objects.filter(
            layer=self.layer, dataset_metadata=superseded,
            is_internal=False).exists(),
            'the relation to the record this link no longer resolves to '
            'stays in the graph forever - nothing removed it before #1261')
        self.assertTrue(MetadataRelation.objects.filter(
            layer=self.layer, dataset_metadata=replacement).exists())

        # what the collection does not own stays
        self.assertTrue(MetadataRelation.objects.filter(
            feature_type=self.feature_type,
            dataset_metadata=superseded).exists(),
            'the superseded record keeps the coupling of the other element '
            'which describes this link')
        self.assertEqual(self.relations(superseded).count(), 2,
                         'the superseded record keeps its relation to the '
                         'feature type and to the curator')
        self.assertTrue(MetadataRelation.objects.filter(
            pk=curated.pk, layer=self.layer,
            origin=MetadataOriginEnum.EDITOR.value,
            is_internal=True).exists())

    def test_the_outcome_without_a_record_keeps_existing_relations(self):
        """A failed collection removes nothing: there is no replacement."""
        remote_metadata = self.reference(DATASET)
        record = remote_metadata.create_metadata_instance()

        broken = self.reference(
            document_without_file_identifier(),
            link="http://example.gov/md/broken")
        self.assertIsNone(broken.create_metadata_instance())

        self.assertTrue(MetadataRelation.objects.filter(
            layer=self.layer, dataset_metadata=record).exists())


class RelationColumnMappingTests(CollectionHarness, TestCase):
    """The explicit mapping which fails loudly instead of defaulting to silence."""

    def test_every_described_kind_of_a_reference_has_a_column(self):
        """Every RemoteMetadata kind can couple what it describes."""
        described = {
            model._meta.get_field("describes").related_model.__name__
            for model in apps.get_models()
            if issubclass(model, RemoteMetadata)
            and model is not RemoteMetadata and not model._meta.abstract
        }
        self.assertTrue(described,
                        'no RemoteMetadata kind found - did the registry move?')
        self.assertTrue(
            described <= set(MetadataRelation.DESCRIBED_OBJECT_FIELDS),
            f"described kinds without a column: "
            f"{described - set(MetadataRelation.DESCRIBED_OBJECT_FIELDS)}")

    def test_add_refuses_a_described_class_without_a_column(self):
        """The silence of the old chain wrote a half relation (#1261)."""
        record = DatasetMetadataRecord.objects.first() or \
            DatasetMetadataRecord()
        with self.assertRaises(ValueError) as refused:
            record.add_metadata_relation(related_object=record)
        self.assertIn("DatasetMetadataRecord", str(refused.exception))

    def test_add_refuses_a_record_type_without_a_column(self):
        """A record type without a column of its own is refused, not half
        stored: MetadataRelation has no application column."""
        application = ApplicationMetadataRecord()
        with self.assertRaises(ValueError) as refused:
            application.add_metadata_relation(related_object=self.layer)
        self.assertIn("ApplicationMetadataRecord", str(refused.exception))

    def test_remove_refuses_an_unknown_described_class(self):
        """remove_metadata_relation used to answer an unknown class by
        silently removing nothing (#1261)."""
        record = DatasetMetadataRecord()
        with self.assertRaises(ValueError):
            record.remove_metadata_relation(
                related_object=None, internal=False,
                origin=MetadataOriginEnum.CAPABILITIES.value)

    def test_remove_takes_back_exactly_the_cited_coupling(self):
        """The method which nothing called now closes the collection loop."""
        remote_metadata = self.reference(DATASET)
        record = remote_metadata.create_metadata_instance()
        self.assertEqual(self.relations(record).count(), 1)

        record.remove_metadata_relation(
            related_object=self.layer, internal=False,
            origin=MetadataOriginEnum.CAPABILITIES.value)
        self.assertEqual(self.relations(record).count(), 0)
