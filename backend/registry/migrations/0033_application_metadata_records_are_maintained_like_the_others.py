"""The new record type is held by the database rules which already maintain the others.

``0021``, ``0024`` and ``0025`` write their rules for the record types which exist on
the day they run: the sync trigger is attached to one keywords relation, the keep
trigger to one record table, the diff size to one audit table, and the fan-out of a
keyword rename is a list of record tables written into the body of its function. A
record type created afterwards is not covered by any of them. For
``ApplicationMetadataRecord`` that would not be a missing optimisation but a wrong
row: its ``keywords_list`` is a column the record really has, it is one of the columns
the stored ``search_vector`` of ``0022`` is tokenized from, and both the audit rows and
the per-day statistics read the diff size -- so an application record would answer no
keyword, would be unfindable by its own keywords and would report a change as no
change.

Therefore this migration only attaches the new tables to rules which already exist.
The two keywords triggers EXECUTE the very functions of ``0021`` and ``0024``, which
take the relation and its foreign key as trigger arguments precisely so that one
function serves every record type; the diff size repeats ``0025`` for the one audit
table it did not know. Only the fan-out of a rename has to be written again, because
its statement names the record tables: the function of ``0021`` is replaced by the same
function which knows one more table, and rolling this migration back restores the
statement as ``0021`` wrote it.

Nothing is backfilled: the tables arrive empty and the triggers are in place before
the first row can be written.

"""

from django.db import migrations

# the record type of this migration, as (record table, table of its keywords
# relation, foreign key of that relation) -- the same triple 0021 lists for the
# types it knows
RECORD = "registry_applicationmetadatarecord"
RELATION = "registry_applicationmetadatarecord_keywords"
FOREIGN_KEY = "applicationmetadatarecord_id"

# the record types a keyword rename reaches from here on, in the order the function
# of 0021 lists them and with the application record appended
MAINTAINED_RECORD_TYPES = [
    ("registry_datasetmetadatarecord",
     "registry_datasetmetadatarecord_keywords", "datasetmetadatarecord_id"),
    ("registry_servicemetadatarecord",
     "registry_servicemetadatarecord_keywords", "servicemetadatarecord_id"),
    (RECORD, RELATION, FOREIGN_KEY),
]

# the aggregate answering the keywords of one record -- the very statement of 0021,
# which its triggers, its backfill and the guard of 0024 all write, so that the
# rename fan-out below stores what they store
AGGREGATE = """(SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),
                             '{{}}'::varchar(300)[])
                 FROM {relation} AS relation
                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id
                WHERE relation.{foreign_key} = record.id
                  AND btrim(keyword.keyword) <> '')"""

# the audit table of the new record type with the columns the diff size compares --
# the tracked, editable fields of the record, which is what
# registry.querys.historical.with_delta_size() compares and what 0025 lists
HISTORY_TABLE = "registry_historicalapplicationmetadatarecord"
TRACKED_FIELDS = (
    "access_constraints", "abstract", "application_contact_id", "bounding_geometry",
    "charset", "code", "code_space", "fees", "inspire_interoperability",
    "is_searchable", "licence_id", "license_source_note", "metadata_contact_id",
    "title", "update_frequency_code", "use_limitation",
)

KEYWORDS_SYNC_TRIGGER = """
CREATE TRIGGER {relation}_keywords_list_sync
    AFTER INSERT OR UPDATE OR DELETE ON {relation}
    FOR EACH ROW
    EXECUTE FUNCTION registry_sync_metadatarecord_keywords_list('{record}', '{foreign_key}');
""".format(relation=RELATION, record=RECORD, foreign_key=FOREIGN_KEY)

KEYWORDS_KEEP_TRIGGER = """
CREATE TRIGGER {record}_keywords_list_keep
    BEFORE UPDATE ON {record}
    FOR EACH ROW
    EXECUTE FUNCTION registry_keep_metadatarecord_keywords_list('{relation}', '{foreign_key}');
""".format(record=RECORD, relation=RELATION, foreign_key=FOREIGN_KEY)


def rename_function(tables):
    """The fan-out of a keyword rename over the given record types.

    Written as 0021 writes it, for as many record types as are named: the function
    cannot ask the catalog which tables hold a ``keywords_list``, so a record type
    which wants to be reached by a rename has to be named in its body.
    """
    updates = ""
    for record, relation, foreign_key in tables:
        updates += """        UPDATE {record} AS record
           SET keywords_list = {aggregate};

""".format(
            record=record,
            aggregate=AGGREGATE.format(relation=relation, foreign_key=foreign_key))

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


# the statement of 0025 for one audit table -- predecessor lookup, comparison and
# the trigger which answers the value at insert time, kept as that migration has it
PREDECESSOR_FILTER = """{previous}.id = {row}.id
                   AND ({previous}.history_date, {previous}.history_id)
                       < ({row}.history_date, {row}.history_id)"""

PREDECESSOR_ORDER = "{previous}.history_date DESC, {previous}.history_id DESC"


def comparison(previous, row, columns):
    return "\n                    + ".join(
        "(%s.%s IS DISTINCT FROM %s.%s)::int" % (previous, column, row, column)
        for column in columns)


def selected_columns(alias, columns):
    return ", ".join("{}.{}".format(alias, column) for column in columns)


def function_name(table):
    return "registry_delta_size_" + table[len("registry_"):]


def trigger_name(table):
    return table + "_delta_size"


DIFF_SIZE_FUNCTION = """
CREATE OR REPLACE FUNCTION {function}()
    RETURNS TRIGGER
    LANGUAGE plpgsql
AS $function$
DECLARE
    -- the row this one precedes, if the record has one at all
    previous RECORD;
BEGIN
    SELECT {selected}
      INTO previous
      FROM {table} AS written
     WHERE {filter}
     ORDER BY {order}
     LIMIT 1;

    IF NOT FOUND THEN
        -- nothing to compare with, which is not the same as nothing changed
        NEW.delta_size := NULL;
        RETURN NEW;
    END IF;

    NEW.delta_size := {comparison};
    RETURN NEW;
END;
$function$;
"""

DIFF_SIZE_TRIGGER = """
CREATE TRIGGER {trigger}
    BEFORE INSERT OR UPDATE OF {columns} ON {table}
    FOR EACH ROW
    EXECUTE FUNCTION {function}();
"""

CREATE_SQL = (
    KEYWORDS_SYNC_TRIGGER
    + KEYWORDS_KEEP_TRIGGER
    + rename_function(MAINTAINED_RECORD_TYPES)
    + DIFF_SIZE_FUNCTION.format(
        function=function_name(HISTORY_TABLE),
        table=HISTORY_TABLE,
        selected=selected_columns("written", TRACKED_FIELDS),
        filter=PREDECESSOR_FILTER.format(previous="written", row="NEW"),
        order=PREDECESSOR_ORDER.format(previous="written"),
        comparison=comparison("previous", "NEW", TRACKED_FIELDS))
    + DIFF_SIZE_TRIGGER.format(
        trigger=trigger_name(HISTORY_TABLE),
        table=HISTORY_TABLE,
        columns=", ".join(TRACKED_FIELDS + ("delta_size",)),
        function=function_name(HISTORY_TABLE)))

DROP_SQL = ("""
DROP TRIGGER IF EXISTS {trigger} ON {table};
DROP FUNCTION IF EXISTS {function}();
DROP TRIGGER IF EXISTS {sync} ON {relation};
DROP TRIGGER IF EXISTS {keep} ON {record};
""".format(
    trigger=trigger_name(HISTORY_TABLE), table=HISTORY_TABLE,
    function=function_name(HISTORY_TABLE),
    sync=RELATION + "_keywords_list_sync", relation=RELATION,
    keep=RECORD + "_keywords_list_keep", record=RECORD)
    # the fan-out of 0021 as it was before this record type was named in it
    + rename_function(MAINTAINED_RECORD_TYPES[:2]))


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0032_applicationmetadatarecord_and_more'),
    ]

    operations = [
        migrations.RunSQL(CREATE_SQL, DROP_SQL),
    ]
