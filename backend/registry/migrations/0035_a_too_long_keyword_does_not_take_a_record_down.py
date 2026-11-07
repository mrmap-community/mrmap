"""The functions which maintain the keywords array stop answering a 300 character keyword.

``0028`` widened ``registry_keyword.keyword`` and the ``keywords_list`` of the
records to text, but it never re-declared the trigger functions of ``0021`` and
``0024``: an ``ALTER TYPE`` does not reach into a plpgsql body, and the aggregate
inside them still names its empty-array fallback by the width the columns used to
have -- ``'{}'::varchar(300)[]``, which ``0033`` restated for the record type it
attached. COALESCE resolves one common type over all of its arguments, and on the
cluster which ran the report that resolution lands on the named ``varchar(300)[]``:
every aggregated keyword is re-cast to that width and one keyword over it raises
``value too long for type character varying(300)`` inside the UPDATE the sync
trigger runs -- inside the save of the record. A catalogue which published one
347 character keyword lost three of its records that way (job 40, temporary file
1079625), and every one of them is exactly what ``0028`` had set out to make
impossible. Newer clusters resolve the very same statement onto the aggregated
``text[]`` and answer nothing, which is why no test on this schema ever noticed:
the function body is wrong whichever way a cluster reads it, and it is the body
the deployed schema keeps.

Therefore this migration re-creates the three functions statement for statement as
``0021``, ``0024`` and ``0033`` wrote them, with one thing answered differently:
the empty array the aggregate falls back to carries the element type the columns
have now, so COALESCE has one type to agree on and nothing is re-cast on the way
into the widened column.

Nothing else is touched, and that is what makes it a migration for a running
deployment: a ``CREATE OR REPLACE FUNCTION`` of a plpgsql function rewrites no
rows and no trigger -- the triggers reach the functions by identity and keep
firing over the replaced bodies. And there is nothing to repair: the failure
refused the record save as a whole, so no array written under the old functions
is behind its relation. The way back installs the bodies exactly as the previous
migrations wrote them, down to the narrow literal and the three record types the
rename fan-out of ``0033`` names.
"""

from django.db import migrations

# the record types which hold a keywords array, as
# (record table, table of its keywords relation, foreign key of that relation) --
# the list of 0033, which is the list of 0021 with the application record appended
MAINTAINED_RECORD_TYPES = [
    ("registry_datasetmetadatarecord",
     "registry_datasetmetadatarecord_keywords", "datasetmetadatarecord_id"),
    ("registry_servicemetadatarecord",
     "registry_servicemetadatarecord_keywords", "servicemetadatarecord_id"),
    ("registry_applicationmetadatarecord",
     "registry_applicationmetadatarecord_keywords", "applicationmetadatarecord_id"),
]

# the aggregate answering the keywords of one record -- the very statement of
# 0021, which its triggers, its backfill and the guard of 0024 all write, with
# only the fallback literal answering the widened column
AGGREGATE = """(SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),
                             '{{}}'::text[])
                 FROM {relation} AS relation
                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id
                WHERE relation.{foreign_key} = record.id
                  AND btrim(keyword.keyword) <> '')"""

# the same statement as 0021 wrote it, so that the way back installs exactly the
# body the deployment had before this migration
PREVIOUS_AGGREGATE = """(SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),
                             '{{}}'::varchar(300)[])
                 FROM {relation} AS relation
                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id
                WHERE relation.{foreign_key} = record.id
                  AND btrim(keyword.keyword) <> '')"""


def inside_sql_literal(statement):
    """The statement as it must appear inside a single quoted sql literal."""
    return statement.replace("'", "''")


def trigger_aggregate(aggregate):
    """The aggregate for the bodies which learn relation and foreign key at run
    time -- written once here and used by both, as 0021 and 0024 each use it."""
    return inside_sql_literal(aggregate.format(relation="%2$I", foreign_key="%3$I"))


def sync_function(aggregate):
    """The function of 0021 which rebuilds the array of one record, for the given
    aggregate."""
    return """
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
""".format(aggregate=trigger_aggregate(aggregate))


def keep_function(aggregate):
    """The guard of 0024 which re-derives the array a write did not read, for the
    given aggregate."""
    return """
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
""".format(aggregate=trigger_aggregate(aggregate))


def rename_function(tables, aggregate):
    """The fan-out of a keyword rename over the given record types, written as
    0021 and 0033 write it: the function cannot ask the catalog which tables hold
    a ``keywords_list``, so a record type which wants to be reached by a rename
    has to be named in its body."""
    updates = ""
    for record, relation, foreign_key in tables:
        updates += """        UPDATE {record} AS record
           SET keywords_list = {aggregate};

""".format(
            record=record,
            aggregate=aggregate.format(relation=relation, foreign_key=foreign_key))

    return """
CREATE OR REPLACE FUNCTION registry_sync_keyword_rename_to_metadatarecords()
    RETURNS TRIGGER
    LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.keyword IS DISTINCT FROM NEW.keyword THEN
{updates}    END IF;

    RETURN NULL;
END;
$$;
""".format(updates=updates)


CREATE_SQL = (
    sync_function(AGGREGATE)
    + keep_function(AGGREGATE)
    + rename_function(MAINTAINED_RECORD_TYPES, AGGREGATE))

# the bodies as 0021, 0024 and 0033 left them -- the narrow literal and all
REVERT_SQL = (
    sync_function(PREVIOUS_AGGREGATE)
    + keep_function(PREVIOUS_AGGREGATE)
    + rename_function(MAINTAINED_RECORD_TYPES, PREVIOUS_AGGREGATE))


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0034_remove_harvestedmetadatarelation_dm_record_or_sm_record_and_more'),
    ]

    operations = [
        migrations.RunSQL(CREATE_SQL, REVERT_SQL),
    ]
