"""The manager semantics of historized services (#1480).

Three separate breaks of the same area, pinned together because each of them
was invisible exactly behind the manager a caller would trust:

* ``CatalogueServiceManager`` was composed with ``Manager.from_queryset(
  DefaultHistoryManager)``: ``from_queryset`` only copies the *public*
  attributes of the queryset, so the manager answered ``stats_per_day`` but
  not the private helper that method calls - the catalogue answer was an
  AttributeError the moment it was evaluated. ``LayerManager`` beside it
  inherited the class instead, which is what works;
* a plain ``DefaultHistoryManager`` was *declared* on the models as ``history``
  next to ``change_log = HistoricalRecords(...)``. simple_history binds the
  audit accessor to the name of that declaration, so ``Model.history`` was
  this manager while the records lived under ``change_log`` - and it answered
  **current** rows to every ``.history.filter`` or ``.history.count`` written
  later: the shape of an audit read, the contents of the live table. The
  accessor of these helpers is ``change_stats`` now, and audit rows are
  reached through ``change_log``, where simple_history put them;
* ``HistoricalRecordMixin.save`` read its first positional argument as
  ``without_historical``, which are Django's ``force_insert`` and
  ``force_update`` positions - every ``save(True)`` anywhere would have
  written no audit row instead of a forced INSERT. The switch is keyword-only.
"""
from django.test import TestCase

from extras.managers import DefaultHistoryManager
from registry.models.metadata import MetadataContact, ServiceMetadataRecord
from registry.models.service import CatalogueService, Layer, WebMapService


class CatalogueServiceManagerTests(TestCase):
    """The manager of the catalogue answers its own public surface."""

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Manager semantics contact')
        cls.service = CatalogueService.objects.create(
            title='Catalogue of the manager test', version=202, origin=1,
            service_url='https://example.com/csw',
            metadata_contact=contact, service_contact=contact)

    def test_the_history_helpers_survive_the_queryset_composition(self):
        """`stats_per_day` *evaluates*, which is what the endpoint does.

        The broken composition answered the attribute and failed inside it on
        the private helper `from_queryset` does not copy, so looking the
        method up proves nothing - the aggregation has to be run.
        """
        self.assertIsInstance(
            CatalogueService.objects, DefaultHistoryManager,
            'the history helpers must be inherited, not copied')

        rows = list(CatalogueService.objects.stats_per_day())

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]['id'], self.service.change_log.first().history_day)

    def test_the_manager_that_inherits_the_pattern_still_works(self):
        """The LayerManager this fix copies keeps working beside it."""
        self.assertIsInstance(Layer.objects, DefaultHistoryManager)


class HistoryAccessorNameTests(TestCase):
    """Audit rows live under `change_log`, current rows never under `history`."""

    MODELS = (WebMapService, CatalogueService, ServiceMetadataRecord)

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Accessor test contact')
        cls.service = WebMapService.objects.create(
            title='Live and counted', version=130, origin=1,
            service_url='https://example.com/wms',
            metadata_contact=contact, service_contact=contact)

    def test_the_audit_accessor_answers_the_historical_rows(self):
        """After one create, `change_log` holds the audit row, not the service.

        simple_history binds the accessor to the name the records are declared
        under - which is why the manager of the helpers may never be declared
        as `history`: readers naturally write `.history` expecting exactly
        this, the audit side, and the old declaration answered it the live
        table.
        """
        historical = WebMapService.change_log.first()

        self.assertIsNotNone(historical, 'the create wrote no audit row')
        self.assertIsInstance(
            historical, WebMapService.change_log.model,
            'change_log answered a row of the live table')
        self.assertNotIsInstance(historical, WebMapService)

    def test_history_never_answers_current_rows(self):
        """Where a `history` attribute exists, it is not the live-table manager.

        The trap was a name collision, not a missing method: the assertion is
        about what the name must never mean again, so it tolerates the
        accessor being absent (this project's declaration name is
        `change_log`) but never answering the current rows.
        """
        for model in self.MODELS:
            accessor = getattr(model, 'history', None)
            if accessor is not None:
                self.assertNotIsInstance(
                    accessor, DefaultHistoryManager,
                    f'{model.__name__}.history answers current rows')

    def test_the_statistics_accessor_is_change_stats(self):
        """The aggregation helpers live under a name that says what they are."""
        for model in self.MODELS:
            self.assertIsInstance(
                model.change_stats, DefaultHistoryManager,
                f'{model.__name__} lost its statistics accessor')


class SaveSignatureTests(TestCase):
    """The positional arguments of `save` are Django's, always (#1480)."""

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Save signature contact')
        cls.service = WebMapService.objects.create(
            title='Forced once', version=130, origin=1,
            service_url='https://example.com/wms/forced',
            metadata_contact=contact, service_contact=contact)

    def test_a_positional_save_is_djangos_own_positional_save(self):
        """``save(True)`` reaches Django; it is not swallowed as the audit switch.

        With the old signature the positional landed in `without_historical`
        and every such save of the whole framework silently wrote its row
        without an audit record - an interpretation the caller never asked
        for. The keyword-only signature hands the argument to Django instead,
        which answers by its own contract (since Django 5 the force flags are
        keyword-only): a loud TypeError. Loud and wrong-argument is honest;
        silent and audit-less is the break this pins closed.
        """
        self.assertEqual(WebMapService.change_log.count(), 1)

        again = WebMapService.objects.get(pk=self.service.pk)
        with self.assertRaises(TypeError):
            again.save(True)

        # nothing was written by the refused call
        self.assertEqual(WebMapService.change_log.count(), 1)
        self.assertEqual(
            WebMapService.objects.get(pk=self.service.pk).title,
            'Forced once')

    def test_the_switch_still_works_as_a_keyword(self):
        """`without_historical=True` skips the audit row, as its name says."""
        service = WebMapService.objects.get(pk=self.service.pk)
        service.title = 'changed without the audit row'
        service.save(without_historical=True)

        self.assertEqual(WebMapService.change_log.count(), 1)
        self.assertEqual(
            WebMapService.objects.get(pk=self.service.pk).title,
            'changed without the audit row')
