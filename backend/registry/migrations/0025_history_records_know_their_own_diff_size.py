"""Every audit row knows how many fields it changed, from the moment it exists.

The per-day statistics answer one question per audit row: how many tracked
fields does it differ in from the row which precedes it. Until now that was
answered at read time -- ``DefaultHistoryManager._stats_per_day_queryset()``
found each row's predecessor with a correlated subquery and compared every
tracked field of the two through ``IS DISTINCT FROM``, which is audit rows times
tracked fields of work per request. Seven charts on one dashboard page did that
until the dashboard was served from a materialized view instead, rebuilt on a
schedule, which is how the nine statistics views of #851 came to exist at all.

The answer is known the instant the row is written and it never changes again:
audit rows are never updated, and the row they are compared against is already
in the table. So it is written at insert time and read as a plain column.

It lives in the database rather than in a ``pre_save`` hook or a
``create_historical_record`` override because none of those reach every writer.
``bulk_create_with_history()``, which the WMS and WFS mapper configs select as
``_create_mode``, ends in ``bulk_history_create()`` which ends in
``objects.bulk_create()`` -- no signals, no ``save()``, no library hook -- and
that is the harvesting path, which is the path producing the most audit rows.
Same reason ``0021`` and ``0024`` gave for their triggers: the writer which does
not know about the column must not be able to leave it wrong.

The comparison covers exactly the columns ``with_delta_size()`` has always
compared -- the tracked fields of the record which are editable, as raw
foreign key ids -- so the numbers the statistics answer do not move. Two of its
details carry over deliberately:

* A row without a predecessor has no diff size at all rather than zero. That is
  what tells a record which was created before history existed apart from a
  record which was saved without changing anything, and the statistics count
  only the first as new.
* A delete row is compared too. It carries the values of its predecessor, so it
  answers zero; what makes it a delete is its ``history_type``, never its diff.

The predecessor is looked up by ``(history_date, history_id)``, the very
comparison ``with_prev_record_id()`` uses, so two rows of one record written by
one statement -- which is what a bulk harvest does -- are still in front of each
other. A ``BEFORE INSERT`` trigger sees the rows an inserting statement has
already placed, which is what makes the bulk path answer the same as a save.
And because the value is derived from the tracked fields, the trigger is a
``BEFORE INSERT OR UPDATE OF`` those fields: a writer which rewrites a row
without knowing the column -- ``loaddata`` is the one that matters, see
``diff_size_trigger`` -- gets it computed again instead of writing a value no
predecessor answers.

The backfill is one pass per table which answers each row from its predecessor
in the same statement the trigger answers from, so the two cannot disagree, and
it writes only the rows whose value is not already right: running it again costs
reads and writes nothing.
"""

from django.db import migrations, models

# the audit tables which answer their own diff size, with the columns the
# comparison covers -- the tracked, editable fields of the record, which is
# what registry.querys.historical.with_delta_size() compares
HISTORY_TABLES = {
    "registry_historicaldatasetmetadatarecord": (
        "access_constraints", "abstract", "bounding_geometry", "charset",
        "code", "code_space", "dataset_contact_id", "fees", "format",
        "inspire_interoperability", "inspire_top_consistence",
        "is_searchable", "licence_id", "license_source_note",
        "lineage_statement", "metadata_contact_id", "preview_image", "title",
        "update_frequency_code", "use_limitation",
    ),
    "registry_historicalservicemetadatarecord": (
        "access_constraints", "abstract", "bounding_geometry", "charset",
        "code", "code_space", "fees", "inspire_interoperability",
        "is_searchable", "licence_id", "license_source_note",
        "metadata_contact_id", "title", "use_limitation",
    ),
    "registry_historicalwebmapservice": (
        "access_constraints", "abstract", "fees", "is_active", "is_searchable",
        "licence_id", "license_source_note", "metadata_contact_id",
        "service_contact_id", "title", "use_limitation",
    ),
    "registry_historicalwebfeatureservice": (
        "access_constraints", "abstract", "fees", "is_active", "is_searchable",
        "licence_id", "license_source_note", "metadata_contact_id",
        "service_contact_id", "title", "use_limitation",
    ),
    "registry_historicalcatalogueservice": (
        "access_constraints", "abstract", "fees", "is_active", "is_searchable",
        "licence_id", "license_source_note", "max_step_size",
        "metadata_contact_id", "service_contact_id", "title",
        "use_limitation",
    ),
    "registry_historicallayer": (
        "abstract", "is_active", "is_searchable", "preview_image", "title",
    ),
    "registry_historicalfeaturetype": (
        "abstract", "default_reference_system_id",
        "describe_feature_type_document", "is_active", "is_searchable", "title",
    ),
}

# the row of the same record which was written just before another one: the
# very comparison with_prev_record_id() uses, tuple and tie breaker included,
# so that two rows of one record written by one statement are still in front of
# each other -- {previous} is the older row, {row} the one being answered for
PREDECESSOR_FILTER = """{previous}.id = {row}.id
                   AND ({previous}.history_date, {previous}.history_id)
                       < ({row}.history_date, {row}.history_id)"""

PREDECESSOR_ORDER = "{previous}.history_date DESC, {previous}.history_id DESC"


def comparison(previous, row, columns):
    """How many of the given columns the two rows differ in.

    ``IS DISTINCT FROM`` per column, so that a field which is empty on both
    sides counts as unchanged and one which is empty on one side counts as a
    change -- the same two decisions ``IsDistinctFrom()`` encodes.
    """
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


def diff_size_trigger(table, columns):
    """The trigger which writes the diff size of a row of one audit table.

    ``UPDATE OF`` the compared fields, and not every update of the row: the
    value is derived from those fields and from nothing else, so a statement
    which writes another column of the row leaves the answer it already has
    alone, while a statement which writes the data the answer is computed out
    of has it computed again.

    That half is not decoration. ``loaddata`` ends in ``save_base(raw=True)``
    without ``update_fields``, which writes every column of the row from the
    instance the fixture built -- so a column the fixture does not name is
    written as its default. A second load of the same fixture, which is what
    every behave feature asking for ``test_wms.json`` does (thirty of them do)
    and what restoring a dump of a deployment does, used to reset the column of
    every audit row it touched. ``delta_size`` is named next to the compared
    fields so that a write of the answer alone is answered by the database too:
    the column is not a writer's to set.
    """
    return """
CREATE TRIGGER {trigger}
    BEFORE INSERT OR UPDATE OF {columns} ON {table}
    FOR EACH ROW
    EXECUTE FUNCTION {function}();
""".format(trigger=trigger_name(table), table=table,
           columns=", ".join(tuple(columns) + ("delta_size",)),
           function=function_name(table))


def backfill(table, columns):
    """The diff size of every row already in the table.

    One statement per table answering each row from its predecessor exactly the
    way the trigger does. The predicate which compares the value it computed
    with the value stored is what makes the statement safe to run twice.
    """
    return """
UPDATE {table} AS audit
   SET delta_size = computed.delta_size
  FROM (
    SELECT audit.history_id,
           CASE WHEN previous.history_id IS NULL THEN NULL
                ELSE {comparison}
           END AS delta_size
      FROM {table} AS audit
      LEFT JOIN LATERAL (
          SELECT predecessor.history_id, {selected}
            FROM {table} AS predecessor
           WHERE {filter}
           ORDER BY {order}
           LIMIT 1
      ) AS previous ON TRUE
  ) AS computed
 WHERE computed.history_id = audit.history_id
   AND computed.delta_size IS DISTINCT FROM audit.delta_size;
""".format(
        table=table,
        comparison=comparison("previous", "audit", columns),
        selected=selected_columns("predecessor", columns),
        filter=PREDECESSOR_FILTER.format(previous="predecessor", row="audit"),
        order=PREDECESSOR_ORDER.format(previous="predecessor"))


CREATE_SQL = "".join(
    DIFF_SIZE_FUNCTION.format(
        function=function_name(table),
        table=table,
        selected=selected_columns("written", columns),
        filter=PREDECESSOR_FILTER.format(previous="written", row="NEW"),
        order=PREDECESSOR_ORDER.format(previous="written"),
        comparison=comparison("previous", "NEW", columns),
    ) + diff_size_trigger(table, columns)
    for table, columns in HISTORY_TABLES.items()
)

BACKFILL_SQL = "".join(
    backfill(table, columns) for table, columns in HISTORY_TABLES.items())

# Undoing this migration has to drop the column, and a per-day statistics view
# which was answered from it is in the way: a materialized view holds a
# dependency on every column its statement reads, and since the diff size is a
# column now, the views of the resources which read it depend on it. Which views
# those are is asked of the database rather than written down: the views are what
# django-pgviews recreates from the code once the migration is through, so the
# ones standing in the way are exactly the ones which happen to exist -- and once
# #857 has dropped them this finds nothing to drop. The dependency of a view on a
# column of its table is recorded for its rewrite rule, which is why the rule is
# joined in to reach the view itself.
DROP_STATISTICS_VIEWS_SQL = """
DO $$
DECLARE
    dependent text;
BEGIN
    FOR dependent IN
        SELECT DISTINCT dependent_view.oid::regclass::text
          FROM pg_attribute AS field
          JOIN pg_depend AS dependence
            ON dependence.refclassid = 'pg_class'::regclass
           AND dependence.refobjid = field.attrelid
           AND dependence.refobjsubid = field.attnum
          LEFT JOIN pg_rewrite AS rule ON rule.oid = dependence.objid
          JOIN pg_class AS dependent_view
            ON dependent_view.oid = COALESCE(rule.ev_class, dependence.objid)
           AND dependent_view.relkind = 'm'
         WHERE field.attname = 'delta_size'
    LOOP
        EXECUTE format('DROP MATERIALIZED VIEW %s', dependent);
    END LOOP;
END;
$$;
"""

DROP_SQL = "".join(
    "DROP TRIGGER IF EXISTS {} ON {};\n".format(trigger_name(table), table)
    + "DROP FUNCTION IF EXISTS {}();\n".format(function_name(table))
    for table, _columns in HISTORY_TABLES.items()
)


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0024_keep_the_keywords_list_of_a_record_on_every_write'),
    ]

    operations = [
        migrations.AddField(
            model_name='historicalcatalogueservice',
            name='delta_size',
            field=models.PositiveSmallIntegerField(
                editable=False, null=True, verbose_name='delta size',
                help_text='how many tracked fields this record differs in from '
                          'the record which precedes it, empty without a '
                          'predecessor'),
        ),
        migrations.AddField(
            model_name='historicaldatasetmetadatarecord',
            name='delta_size',
            field=models.PositiveSmallIntegerField(
                editable=False, null=True, verbose_name='delta size',
                help_text='how many tracked fields this record differs in from '
                          'the record which precedes it, empty without a '
                          'predecessor'),
        ),
        migrations.AddField(
            model_name='historicalfeaturetype',
            name='delta_size',
            field=models.PositiveSmallIntegerField(
                editable=False, null=True, verbose_name='delta size',
                help_text='how many tracked fields this record differs in from '
                          'the record which precedes it, empty without a '
                          'predecessor'),
        ),
        migrations.AddField(
            model_name='historicallayer',
            name='delta_size',
            field=models.PositiveSmallIntegerField(
                editable=False, null=True, verbose_name='delta size',
                help_text='how many tracked fields this record differs in from '
                          'the record which precedes it, empty without a '
                          'predecessor'),
        ),
        migrations.AddField(
            model_name='historicalservicemetadatarecord',
            name='delta_size',
            field=models.PositiveSmallIntegerField(
                editable=False, null=True, verbose_name='delta size',
                help_text='how many tracked fields this record differs in from '
                          'the record which precedes it, empty without a '
                          'predecessor'),
        ),
        migrations.AddField(
            model_name='historicalwebfeatureservice',
            name='delta_size',
            field=models.PositiveSmallIntegerField(
                editable=False, null=True, verbose_name='delta size',
                help_text='how many tracked fields this record differs in from '
                          'the record which precedes it, empty without a '
                          'predecessor'),
        ),
        migrations.AddField(
            model_name='historicalwebmapservice',
            name='delta_size',
            field=models.PositiveSmallIntegerField(
                editable=False, null=True, verbose_name='delta size',
                help_text='how many tracked fields this record differs in from '
                          'the record which precedes it, empty without a '
                          'predecessor'),
        ),
        # the triggers go first: from here on every row that arrives is answered
        # by them, and the backfill below leaves those rows alone
        migrations.RunSQL(CREATE_SQL, DROP_SQL),
        migrations.RunSQL(BACKFILL_SQL, migrations.RunSQL.noop),
        # answers nothing going forward and is the first thing undone coming
        # back, which is where a statistics view built from the column would
        # otherwise keep it from being dropped. A deployment which rolls back
        # therefore stands without those views until it migrates forward again:
        # the code which recreates them on post_migrate reads the column this
        # revision removed, so it reports them missing and cannot answer them --
        # which is what a rollback of the column means while the views of #857
        # are still in the code
        migrations.RunSQL(migrations.RunSQL.noop, DROP_STATISTICS_VIEWS_SQL),
    ]
