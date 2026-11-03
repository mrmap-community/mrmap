"""The keywords of a metadata record as a column which the database maintains.

Aggregating the keywords relation is not expressible as a column expression, so a
record which is searchable by keyword needs the keywords *of the record row*. This
migration keeps the two sides in sync in the database: the array is rebuilt by a
trigger on the keywords relation of every record type which declares it, so that
every writer keeps it honest -- the orm, a bulk ``.set()`` or plain sql -- and no
application code has to know that it exists.

The array holds exactly what a searchable projection used to aggregate: the
distinct keywords of the record without blank entries, ordered by the keyword
itself. ``btrim(keyword) <> ''`` stands in for the ``~ '^\\s*$'`` exclusion of such
a projection; ``registry_keyword`` has not allowed a blank keyword since
``0016_enforce_non_blank_keywords``.

A rename of a keyword is the one change which does not pass through the keywords
relation, so it is fanned out from the keyword itself. This is a set based update
over the records holding the old keyword and is meant to be rare: it is an
administrative edit, not a harvesting path.

The backfill runs in the migration's transaction, so on a deployment with a large
number of metadata records this migration is one long ``UPDATE`` over both record
tables. It writes one new row version per record and no table scan of the keywords
relation beyond the aggregate itself.
"""

import django.contrib.postgres.fields
from django.db import migrations, models

# the record types which declare keywords_list, as
# (record table, table of its keywords relation, foreign key of that relation)
MAINTAINED_RECORD_TYPES = [
    ("registry_datasetmetadatarecord",
     "registry_datasetmetadatarecord_keywords", "datasetmetadatarecord_id"),
    ("registry_servicemetadatarecord",
     "registry_servicemetadatarecord_keywords", "servicemetadatarecord_id"),
]

# the aggregate answering the keywords of one record; written once and used by the
# trigger, the keyword rename fan-out and the backfill, so that all three store the
# very same value
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
# so they are passed through format() as identifiers
TRIGGER_AGGREGATE = inside_sql_literal(
    AGGREGATE.format(relation="%2$I", foreign_key="%3$I"))

SYNC_FUNCTION = """
CREATE OR REPLACE FUNCTION registry_sync_metadatarecord_keywords_list()
    RETURNS TRIGGER
    LANGUAGE plpgsql
AS $$
DECLARE
    -- the record table and the foreign key of the relation the trigger fires on,
    -- given as trigger arguments so that one function serves every record type
    record_table text := TG_ARGV[0];
    foreign_key  text := TG_ARGV[1];
    record_id    uuid;
BEGIN
    -- the key is read through jsonb: the column the trigger needs is only known
    -- at run time and a record parameter cannot be addressed by a field name
    SELECT (to_jsonb(CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END) ->> foreign_key)::uuid
      INTO record_id;

    IF NOT FOUND OR record_id IS NULL THEN
        RETURN NULL;
    END IF;

    EXECUTE format(
        'UPDATE %1$I AS record
            SET keywords_list = {aggregate}
          WHERE record.id = $1',
        record_table, TG_TABLE_NAME, foreign_key
    ) USING record_id;

    RETURN NULL;
END;
$$;
""".format(aggregate=TRIGGER_AGGREGATE)

RENAME_FUNCTION = """
CREATE OR REPLACE FUNCTION registry_sync_keyword_rename_to_metadatarecords()
    RETURNS TRIGGER
    LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.keyword IS DISTINCT FROM NEW.keyword THEN
        UPDATE registry_datasetmetadatarecord AS record
           SET keywords_list = {dataset_aggregate};

        UPDATE registry_servicemetadatarecord AS record
           SET keywords_list = {service_aggregate};
    END IF;

    RETURN NULL;
END;
$$;
""".format(
    dataset_aggregate=AGGREGATE.format(
        relation="registry_datasetmetadatarecord_keywords",
        foreign_key="datasetmetadatarecord_id"),
    service_aggregate=AGGREGATE.format(
        relation="registry_servicemetadatarecord_keywords",
        foreign_key="servicemetadatarecord_id"),
)


def sync_trigger_name(relation_table):
    return relation_table + "_keywords_list_sync"


SYNC_TRIGGERS = ["""
CREATE TRIGGER {trigger}
    AFTER INSERT OR UPDATE OR DELETE ON {relation}
    FOR EACH ROW
    EXECUTE FUNCTION registry_sync_metadatarecord_keywords_list('{record}', '{foreign_key}');
""".format(
    trigger=sync_trigger_name(relation),
    relation=relation,
    record=record,
    foreign_key=foreign_key)
    for record, relation, foreign_key in MAINTAINED_RECORD_TYPES]

RENAME_TRIGGER = """
CREATE TRIGGER registry_keyword_sync_to_metadatarecords
    AFTER UPDATE OF keyword ON registry_keyword
    FOR EACH ROW
    EXECUTE FUNCTION registry_sync_keyword_rename_to_metadatarecords();
"""

BACKFILL = "".join("""
UPDATE {record} AS record
   SET keywords_list = {aggregate};
""".format(
    record=record,
    aggregate=AGGREGATE.format(relation=relation, foreign_key=foreign_key))
    for record, relation, foreign_key in MAINTAINED_RECORD_TYPES)

CREATE_SQL = "".join(
    [SYNC_FUNCTION, RENAME_FUNCTION] + SYNC_TRIGGERS + [RENAME_TRIGGER, BACKFILL])

DROP_SQL = "".join([
    "DROP TRIGGER IF EXISTS registry_keyword_sync_to_metadatarecords ON registry_keyword;\n",
    "DROP FUNCTION IF EXISTS registry_sync_keyword_rename_to_metadatarecords();\n",
] + ["""
DROP TRIGGER IF EXISTS {trigger} ON {relation};
""".format(trigger=sync_trigger_name(relation), relation=relation)
     for _record, relation, _foreign_key in MAINTAINED_RECORD_TYPES] + [
    "DROP FUNCTION IF EXISTS registry_sync_metadatarecord_keywords_list();\n",
])


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0020_harvestingjob_background_process_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='datasetmetadatarecord',
            name='keywords_list',
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=300), default=list, editable=False, size=None),
        ),
        migrations.AddField(
            model_name='servicemetadatarecord',
            name='keywords_list',
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=300), default=list, editable=False, size=None),
        ),
        migrations.RunSQL(CREATE_SQL, DROP_SQL),
    ]
