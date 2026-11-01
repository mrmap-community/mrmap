"""The keywords array of a record survives a write which does not know about it.

``0021`` keeps ``keywords_list`` in sync from the keywords relation, which reaches
every writer that changes that relation. It does not reach a writer which writes the
*record row* with a value for the array that it never read: the column has a default,
so a full ``UPDATE`` of an instance which was built rather than loaded -- from a
fixture, from a partial document, with ``Model(pk=...)`` -- carries an empty array and
overwrites what the trigger maintains. The row ends up holding no keyword while its
keywords relation is untouched, and because the array is one of the columns the search
vector of ``0022`` is tokenized from, the record stops being findable by its own
keywords without anything looking wrong.

That is not hypothetical. ``manage.py loaddata`` saves a deserialized instance through
``Model.save_base(raw=True)``, which no ``save()`` override can intercept, and a
fixture never names a column it does not know about -- so loading the records of a
fixture a second time into the same database, which is what a Behave run that keeps
its test database does, lost the keywords of those records. This is what
``tests/behave/features/csw/get_records.feature`` ran into first, because it is the
feature which loads them.

So the guard lives in the database, next to the value: a ``BEFORE UPDATE`` trigger
which re-derives the array whenever a write brings anything but the value already
stored. A writer which carries the stored value -- a record which was read and saved,
which is every harvesting path -- is answered without the aggregate and without a
second thought; a writer which brings something else gets the value the relation
says. And because the trigger runs before the row is written, the generated
``search_vector`` is computed from the array which is actually stored: a stored
generated column is computed from the new tuple as the before-triggers left it, which
is what makes this the only place the guard can live.

Nothing is repaired by this migration: the column it protects was added by ``0021``,
which has not been released, so no migrated database holds an array which this
trigger would have kept.
"""

from django.db import migrations

# the record types which declare keywords_list, as
# (record table, table of its keywords relation, foreign key of that relation)
MAINTAINED_RECORD_TYPES = [
    ("registry_datasetmetadatarecord",
     "registry_datasetmetadatarecord_keywords", "datasetmetadatarecord_id"),
    ("registry_servicemetadatarecord",
     "registry_servicemetadatarecord_keywords", "servicemetadatarecord_id"),
]

# the aggregate answering the keywords of one record -- the very statement of
# 0021, which is what both of its triggers and its backfill write, so the guard
# restores exactly the value the sync maintains
AGGREGATE = """(SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),
                             '{{}}'::varchar(300)[])
                 FROM {relation} AS relation
                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id
                WHERE relation.{foreign_key} = record.id
                  AND btrim(keyword.keyword) <> '')"""


def inside_sql_literal(statement):
    """The statement as it must appear inside a single quoted sql literal."""
    return statement.replace("'", "''")


# inside the trigger the relation and its foreign key are only known at run time,
# so they are passed through format() as identifiers: %2$I and %3$I are the two
# trigger arguments, %1$I in the statement below is the record table itself
TRIGGER_AGGREGATE = inside_sql_literal(
    AGGREGATE.format(relation="%2$I", foreign_key="%3$I"))

KEEP_FUNCTION = """
CREATE OR REPLACE FUNCTION registry_keep_metadatarecord_keywords_list()
    RETURNS TRIGGER
    LANGUAGE plpgsql
AS $$
DECLARE
    -- the table of the keywords relation and its foreign key, given as trigger
    -- arguments so that one function serves every record type
    relation    text := TG_ARGV[0];
    foreign_key text := TG_ARGV[1];
    -- the type the column has, without naming its length: what the aggregate
    -- answers is what the column stores
    maintained  text[];
BEGIN
    -- the array belongs to the database, so a value which differs from the stored
    -- one is not a change but a write which did not read the column: answered from
    -- the relation, never from the write. A writer which carries the stored value
    -- is the common case and is not asked for the aggregate.
    IF NEW.keywords_list IS DISTINCT FROM OLD.keywords_list THEN
        EXECUTE format(
            'SELECT {aggregate} FROM %1$I AS record WHERE record.id = $1',
            TG_TABLE_NAME, relation, foreign_key
        ) INTO maintained USING NEW.id;

        NEW.keywords_list := maintained;
    END IF;

    RETURN NEW;
END;
$$;
""".format(aggregate=TRIGGER_AGGREGATE)


def keep_trigger_name(record_table):
    return record_table + "_keywords_list_keep"


KEEP_TRIGGERS = ["""
CREATE TRIGGER {trigger}
    BEFORE UPDATE ON {record}
    FOR EACH ROW
    EXECUTE FUNCTION registry_keep_metadatarecord_keywords_list('{relation}', '{foreign_key}');
""".format(
    trigger=keep_trigger_name(record),
    record=record,
    relation=relation,
    foreign_key=foreign_key)
    for record, relation, foreign_key in MAINTAINED_RECORD_TYPES]

CREATE_SQL = KEEP_FUNCTION + "".join(KEEP_TRIGGERS)

DROP_SQL = "".join(
    ["""
DROP TRIGGER IF EXISTS {trigger} ON {record};
""".format(trigger=keep_trigger_name(record), record=record)
     for record, _relation, _foreign_key in MAINTAINED_RECORD_TYPES] + [
        "DROP FUNCTION IF EXISTS registry_keep_metadatarecord_keywords_list();\n"])


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0023_drop_the_searchable_projections_of_a_record'),
    ]

    operations = [
        migrations.RunSQL(CREATE_SQL, DROP_SQL),
    ]
