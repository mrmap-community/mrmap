from django.db import IntegrityError, transaction
from django.test import TestCase
from registry.models.metadata import Keyword


class KeywordConstraintTest(TestCase):
    def test_rejects_blank_and_null_keywords(self):
        for value in ('', ' ', '\t\n', None):
            with self.subTest(keyword=value):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Keyword.objects.create(keyword=value)

    def test_rejects_blank_keywords_in_bulk_create_and_update(self):
        keyword = Keyword.objects.create(keyword='valid')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Keyword.objects.bulk_create([Keyword(keyword='   ')])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Keyword.objects.filter(pk=keyword.pk).update(keyword='')
        keyword.refresh_from_db()
        self.assertEqual(keyword.keyword, 'valid')

    def test_preserves_valid_keyword_text(self):
        for value in ('valid', '  valid  ', 'ümlaut'):
            with self.subTest(keyword=value):
                keyword = Keyword.objects.create(keyword=value)
                keyword.refresh_from_db()
                self.assertEqual(keyword.keyword, value)
