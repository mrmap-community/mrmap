"""The audit diff of a record now counts the profile it was authored under (#1240).

``0025`` wrote the comparison of the per-day statistics as literal sql per audit
table -- the tracked, editable fields of the record, frozen into a column list
("a field a resource starts to track afterwards is a change the numbers would
never count", ``tests_history_delta_size`` holds the list and the models against
each other for exactly that reason). ``0050`` gave the record a ``profile`` and
with it a new tracked editable field, so the three audit tables of the record
types are rewritten here with ``profile_id`` appended to their lists; the
services and layers keep the statements ``0025`` wrote for them untouched.

Nothing is backfilled, unlike ``0025`` itself: the column arrived NULL on every
audit row which exists, so comparing two of them with the new column answers
exactly what the stored ``delta_size`` already answers -- the trigger only has
to see the rows it has not seen yet. And as in ``0033``, rolling this back
restores the very statements ``0025`` and ``0033`` wrote.
"""

from django.db import migrations

# the comparison of 0025 for the three record tables, with profile_id appended --
# the tracked, editable fields of the record as raw foreign key ids
HISTORY_TABLES = {
    "registry_historicaldatasetmetadatarecord": (
        "access_constraints", "abstract", "bounding_geometry", "charset",
        "code", "code_space", "dataset_contact_id", "fees", "format",
        "inspire_interoperability", "inspire_top_consistence",
        "is_searchable", "licence_id", "license_source_note",
        "lineage_statement", "metadata_contact_id", "preview_image", "profile_id",
        "title", "update_frequency_code", "use_limitation",
    ),
    "registry_historicalservicemetadatarecord": (
        "access_constraints", "abstract", "bounding_geometry", "charset",
        "code", "code_space", "fees", "inspire_interoperability",
        "is_searchable", "licence_id", "license_source_note",
        "metadata_contact_id", "profile_id", "title", "use_limitation",
    ),
    "registry_historicalapplicationmetadatarecord": (
        "access_constraints", "abstract", "application_contact_id",
        "bounding_geometry", "charset", "code", "code_space", "fees",
        "inspire_interoperability", "is_searchable", "licence_id",
        "license_source_note", "metadata_contact_id", "profile_id", "title",
        "update_frequency_code", "use_limitation",
    ),
}

# the same three tables as 0025 and 0033 wrote them, for the way back
HISTORY_TABLES_BEFORE = {
    "registry_historicaldatasetmetadatarecord": tuple(
        column for column in HISTORY_TABLES["registry_historicaldatasetmetadatarecord"]
        if column != "profile_id"),
    "registry_historicalservicemetadatarecord": tuple(
        column for column in HISTORY_TABLES["registry_historicalservicemetadatarecord"]
        if column != "profile_id"),
    "registry_historicalapplicationmetadatarecord": tuple(
        column for column in HISTORY_TABLES["registry_historicalapplicationmetadatarecord"]
        if column != "profile_id"),
}

# the predecessor lookup and the statement bodies are the ones of 0025, copied
# as 0033 copied them: a migration does not import another migration's module
PREDECESSOR_FILTER = """{previous}.id = {row}.id
                   AND ({previous}.history_date, {previous}.history_id)
                       < ({row}.history_date, {row}.history_id)"""

PREDECESSOR_ORDER = "{previous}.history_date DESC, {previous}.history_id DESC"


def comparison(previous, row, columns):
    return "\n                    + ".join(
        "(%s.%s IS DISTINCT FROM %s.%s)::int" % (previous, column, row, column)
        for column in columns
    )


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


def trigger_sql(table, columns):
    # the UPDATE OF list is part of the trigger, not of its function, so the
    # trigger itself is replaced and not only the function it executes
    return """
DROP TRIGGER IF EXISTS {trigger} ON {table};
CREATE TRIGGER {trigger}
    BEFORE INSERT OR UPDATE OF {columns} ON {table}
    FOR EACH ROW
    EXECUTE FUNCTION {function}();
""".format(trigger=trigger_name(table), table=table,
           columns=", ".join(tuple(columns) + ("delta_size",)),
           function=function_name(table))


def create_sql(tables):
    return "".join(
        DIFF_SIZE_FUNCTION.format(
            function=function_name(table),
            table=table,
            selected=selected_columns("written", columns),
            filter=PREDECESSOR_FILTER.format(previous="written", row="NEW"),
            order=PREDECESSOR_ORDER.format(previous="written"),
            comparison=comparison("previous", "NEW", columns))
        + trigger_sql(table, columns)
        for table, columns in tables.items())


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0050_a_record_knows_its_profile'),
    ]

    operations = [
        migrations.RunSQL(
            sql=create_sql(HISTORY_TABLES),
            reverse_sql=create_sql(HISTORY_TABLES_BEFORE),
        ),
    ]
