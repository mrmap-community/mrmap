"""Persistence of the lookup tables shared by concurrent imports.

Harvesting imports ~20 metadata files at the same time and every one of them
creates the keywords, contacts and reference systems its document carries. The
tests below keep the properties which make that safe (issue #817): the rows one
import needs go into one insert statement ordered by their unique key, so two
transactions can not wait for each other's entry in the same unique index in
opposite order, and a row another transaction created in the meantime is
skipped instead of aborting the whole import.
"""

from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from random import Random
from threading import Barrier
from unittest.mock import patch

from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from registry.mappers.configs import XPATH_MAP
from registry.mappers.persistence.handler import PersistenceHandler
from registry.mappers.xml_mapper import XmlMapper
from registry.models.metadata import Keyword, MetadataContact


def keyword_specs(mapping):
    """All Keyword specs of a mapping, nested ones included."""
    for value in mapping.values():
        if isinstance(value, dict):
            if value.get('_model') == 'registry.Keyword':
                yield value
            yield from keyword_specs(value)


# the spec the harvesting of a dataset uses, with an xpath which is easy to feed
KEYWORD_SPEC = dict(
    next(keyword_specs(XPATH_MAP[('ISO', 'dataset')])),
    _base_xpath='./Keyword')


def mapper_for_keywords(keywords):
    """A mapper which parsed the keywords in the given order, like a worker
    parses the keywords of one downloaded metadata file."""
    xml = '<root>%s</root>' % ''.join(
        f'<Keyword>{keyword}</Keyword>' for keyword in keywords)
    mapper = XmlMapper(xml, {'keywords': KEYWORD_SPEC})
    mapper.traverse_spec(KEYWORD_SPEC, is_many=True)
    return mapper


def keyword_inserts(context):
    """The statements which wrote keywords during a CaptureQueriesContext."""
    return [
        query['sql'] for query in context.captured_queries
        if query['sql'].startswith('INSERT INTO "registry_keyword"')
    ]


def watch_bulk_create(model_cls, calls):
    """Patches the manager of a model so every bulk_create of the handler is
    recorded with what it was asked to insert, while it still runs."""
    original = model_cls.objects.bulk_create

    def record(objs, **kwargs):
        calls.append(([getattr(obj, 'keyword', obj) for obj in objs], kwargs))
        return original(objs=objs, **kwargs)

    return patch.object(type(model_cls.objects), 'bulk_create',
                        side_effect=record)


class LookupTableInsertTest(TestCase):
    """One import writes the rows it needs as one statement, in key order."""

    def test_one_statement_carries_all_rows_in_key_order(self):
        calls = []
        # the document carries alpha twice and in the order zulu, alpha, mike
        mapper = mapper_for_keywords(['zulu', 'alpha', 'mike', 'alpha'])

        with watch_bulk_create(Keyword, calls), \
                CaptureQueriesContext(connection) as context:
            PersistenceHandler(mapper).persist_all()

        self.assertEqual(len(calls), 1, calls)
        created, kwargs = calls[0]
        self.assertEqual(created, ['alpha', 'mike', 'zulu'])
        self.assertTrue(kwargs.get('ignore_conflicts'), kwargs)

        inserts = keyword_inserts(context)
        self.assertEqual(len(inserts), 1, inserts)
        self.assertIn('ON CONFLICT DO NOTHING', inserts[0])
        self.assertEqual(
            sorted(Keyword.objects.values_list('keyword', flat=True)),
            ['alpha', 'mike', 'zulu'])

    def test_rows_which_already_exist_are_kept_and_returned(self):
        existing = Keyword.objects.create(keyword='alpha')
        Keyword.objects.create(keyword='other')

        final_instances = PersistenceHandler(
            mapper_for_keywords(['alpha', 'beta'])).persist_all()

        self.assertEqual(
            sorted(Keyword.objects.values_list('keyword', flat=True)),
            ['alpha', 'beta', 'other'])
        # the row of the database, not the parsed instance which asked for it
        self.assertEqual(final_instances[Keyword][('alpha',)].pk, existing.pk)

    def test_a_unique_column_which_was_not_parsed_uses_its_default(self):
        """A contact imported without a phone is the contact which stores ''
        there, like the lookup of a single row already treated it."""
        handler = PersistenceHandler(mapper=None)

        handler._persist_get_or_create([MetadataContact(name='mrmap')])
        handler._persist_get_or_create(
            [MetadataContact(name='mrmap', phone=None)])

        self.assertEqual(
            [(contact.name, contact.phone)
             for contact in MetadataContact.objects.filter(name='mrmap')],
            [('mrmap', '')])

    @patch('registry.mappers.persistence.handler.get_key_fields',
           return_value=('id',))
    def test_a_model_without_a_unique_field_is_looked_up_row_by_row(
            self, _get_key_fields):
        """Without a unique field there is nothing to deduplicate, to order by
        or to insert conflict free, so such a model keeps the old lookup."""
        calls = []
        handler = PersistenceHandler(mapper=None)

        with watch_bulk_create(Keyword, calls):
            handler._persist_get_or_create(
                [Keyword(keyword='alpha'), Keyword(keyword='beta')])

        self.assertEqual(calls, [], 'bulk created although there is no key')
        self.assertEqual(
            sorted(Keyword.objects.values_list('keyword', flat=True)),
            ['alpha', 'beta'])


class ConcurrentLookupImportTest(TransactionTestCase):
    """Imports of documents carrying the same new keywords run at the same time.

    Before #817 this is where the unique index of registry_keyword deadlocked:
    the workers inserted the keywords in the order their document carried them,
    so two of them held the entries the other one waited for. The orders are
    shuffled with a fixed seed, so a run which does not deadlock by chance is
    still the same run.
    """

    KEYWORDS = [f'keyword-{index:03d}' for index in range(60)]
    WORKERS = 8

    def import_one_document(self, keywords, start):
        """One worker: one metadata file, one transaction, all starting together."""
        try:
            start.wait(timeout=60)
            with transaction.atomic():
                PersistenceHandler(mapper_for_keywords(keywords)).persist_all()
        except BaseException as exception:
            return exception
        finally:
            connections.close_all()

    def test_the_same_keywords_imported_concurrently(self):
        shuffle = Random(817)
        orders = []
        for _ in range(self.WORKERS):
            keywords = self.KEYWORDS[:]
            shuffle.shuffle(keywords)
            orders.append(keywords)

        start = Barrier(self.WORKERS)
        with ThreadPoolExecutor(max_workers=self.WORKERS) as workers:
            failures = [
                failure for failure in workers.map(
                    self.import_one_document, orders, repeat(start))
                if failure is not None
            ]

        self.assertEqual(failures, [], f'concurrent imports failed: {failures}')
        self.assertEqual(
            sorted(Keyword.objects.values_list('keyword', flat=True)),
            sorted(self.KEYWORDS))
