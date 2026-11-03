"""A keyword is as long as the catalogue which publishes it says it is.

``gmd:keyword`` has no length in ISO 19115, and catalogues publish comma joined
lists which are longer than any column: the file of the report carries one of 347
characters of perfectly good metadata. ``Keyword.keyword`` was a
``varchar(300)`` and its insert raised ``StringDataRightTruncation``; the import
task reads any exception of a file as a record error, marked the file
``has_import_error`` and its records never entered the registry. Four of 411k
files of one import run were lost that way, and every one of them is a loss of
data which the remote never refused (#894).

The column is a ``TextField`` now, like the free text of a record already is
(``abstract``, ``description``, ``access_constraints``). The unique index over it
is the only real limit and it is not a length: postgres stores a truncated key for
a value it toasts, so the index answers a keyword of any length (measured on this
schema: 160,000 bytes inserted into the unique index of a text column with the
default 8 kB block size).

``keywords_list`` of the records has to follow, because it is the same text seen
from the other side: the array is kept in sync from the keywords relation by
``0021`` and ``0024``, and an array of a fixed width would answer another text
than the relation of the very same record - and would refuse the long keyword a
second time, on the write of the record row. Postgres refuses to change the
element type of the array while a stored generated column reads it, which is why
the vector goes first and comes back with the definition and the index the models
answer.

The keyword column is pinned by an object of a different kind: the trigger of
``0021`` which fans a keyword rename out over the records is declared ``AFTER
UPDATE OF keyword``, and naming a column makes the trigger depend on its type -
``cannot alter type of a column used in a trigger definition``. It goes with the
column and comes back with it, statement for statement the one of ``0021``. The
trigger function is not touched, so what the fan-out does is unchanged, and the
migration test renames a long keyword afterwards to keep that the recreated
trigger still fires.

What the migration has to do to the two record tables is what makes it a migration
for a maintenance window and not one for a running deployment, and it is why the
cost is measured and written down: on a synthetic table of 400,000 records of
realistic size - 348 MB of heap, a 49 MB index over the vector - on the defaults of
this deployment,

*   dropping the index and the column of the vector: 0.7 ms and 1.4 ms,
*   widening the array: 106 s, because an array of another element type is *not*
    the change of a type modifier - postgres casts every element and rewrites the
    table,
*   the vector which comes back: 252 s, since it is written out for every row
    which is already there,
*   the index over it: between 49 s and 61 s.

Roughly seven minutes, in one transaction, with the two record tables locked: a
reader sees the old vector until it sees the new one and nothing in between. The
keyword column is not part of that cost - ``varchar(300)`` to ``text`` is the
change of a type modifier, so neither the table nor its unique index is rewritten
(measured: the ``relfilenode`` of both is unchanged, and the index stays valid).

The way back narrows the columns again and therefore fails on a database which
holds a longer keyword than the width it is going back to. That is the price of
having kept metadata which the old schema could not store, and it is the right way
round.
"""

import django.contrib.postgres.fields
import django.contrib.postgres.indexes
import django.contrib.postgres.search
import registry.expressions.search
from django.db import migrations, models

# the record types whose keywords array is widened, with the name of the index over
# the vector of it -- which has to come back under that very same name
RECORD_TYPES = [
    ('datasetmetadatarecord', 'registry_da_search__7a3c56_gin'),
    ('servicemetadatarecord', 'registry_se_search__2b20f5_gin'),
]

KEYWORDS_LIST = django.contrib.postgres.fields.ArrayField(
    base_field=models.TextField(), default=list, editable=False)

SEARCH_VECTOR = models.GeneratedField(
    expression=registry.expressions.search.MetadataRecordSearchVector(),
    output_field=django.contrib.postgres.search.SearchVectorField(),
    db_persist=True)

# the trigger of 0021 which fans a keyword rename out over the records, restated as
# the statement which created it (as 0024 restates the statements of the array it
# keeps). It names the keyword column, so it has to be gone while that column is
# changed - see the module docstring. The function behind it is not re-declared: it
# reads the column, it does not depend on its type.
KEYWORD_RENAME_TRIGGER = """
CREATE TRIGGER registry_keyword_sync_to_metadatarecords
    AFTER UPDATE OF keyword ON registry_keyword
    FOR EACH ROW
    EXECUTE FUNCTION registry_sync_keyword_rename_to_metadatarecords();
"""

DROP_KEYWORD_RENAME_TRIGGER = """
DROP TRIGGER registry_keyword_sync_to_metadatarecords ON registry_keyword;
"""

# the vector of a record is generated from its keywords array, so postgres refuses
# to widen the array while the vector reads it: "cannot alter type of a column used
# by a generated column". The index has to be gone before the column it indexes and
# has to come back after it, and nothing else of the two tables is touched.
OUT_WITH_THE_VECTOR = [
    [
        migrations.RemoveIndex(
            model_name=model_name,
            name=index_name,
        ),
        migrations.RemoveField(
            model_name=model_name,
            name='search_vector',
        ),
    ]
    for model_name, index_name in RECORD_TYPES
]

BACK_WITH_THE_VECTOR = [
    [
        migrations.AddField(
            model_name=model_name,
            name='search_vector',
            field=SEARCH_VECTOR,
        ),
        migrations.AddIndex(
            model_name=model_name,
            index=django.contrib.postgres.indexes.GinIndex(
                fields=['search_vector'], name=index_name),
        ),
    ]
    for model_name, index_name in RECORD_TYPES
]


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0027_files_of_a_job_answer_their_error_count'),
    ]

    operations = [
        *sum(OUT_WITH_THE_VECTOR, []),
        migrations.RunSQL(
            sql=DROP_KEYWORD_RENAME_TRIGGER,
            reverse_sql=KEYWORD_RENAME_TRIGGER,
        ),
        migrations.AlterField(
            model_name='keyword',
            name='keyword',
            field=models.TextField(),
        ),
        migrations.RunSQL(
            sql=KEYWORD_RENAME_TRIGGER,
            reverse_sql=DROP_KEYWORD_RENAME_TRIGGER,
        ),
        migrations.AlterField(
            model_name='datasetmetadatarecord',
            name='keywords_list',
            field=KEYWORDS_LIST,
        ),
        migrations.AlterField(
            model_name='servicemetadatarecord',
            name='keywords_list',
            field=KEYWORDS_LIST,
        ),
        *sum(BACK_WITH_THE_VECTOR, []),
    ]
