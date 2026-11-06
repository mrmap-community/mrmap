"""The keyword maintenance of the records is managed by django-pgtrigger (#1009).

The sync, keep and rename rules of ``0021``, ``0024`` and ``0033`` move from
hand written ``CREATE FUNCTION`` / ``CREATE TRIGGER`` statements to declarative
trigger objects which the makemigrations autodetector sees, so that a change to
one of them arrives as a reviewable migration operation instead of as new sql
boilerplate. This migration transfers the objects of the database: the legacy
functions and triggers are dropped and the equivalent pgtrigger objects -- the
very same statements, written by ``registry/triggers.py`` -- are installed, in
one transaction. ``keywords_list`` never holds anything but the aggregate for a
moment, which is why no backfill is needed. Rolling this migration back
restores the state of ``0034``: the legacy objects are recreated as those
migrations wrote them, reproduced verbatim below.

The three unmanaged models are needed because the trigger of a keywords
relation must be declared on a model, while the auto-created through models of
a ``ManyToManyField`` never enter the migration state; these models only make
the existing relation tables addressable and create nothing (#1009).

The objects of the package carry their own names in the database
(``pgtrigger_<trigger>_<hash>``, listed by ``manage.py pgtrigger ls``); the
legacy names are gone after this migration. The reverse of the trigger
operations drops the triggers but leaves the ``pgtrigger_`` functions, which
are removed by the forward direction of any later trigger change or by
``manage.py pgtrigger uninstall``.
"""

import pgtrigger.compiler
import pgtrigger.migrations
from django.db import migrations, models

import django.db.models.deletion
import registry.triggers

# the record types which declare keywords_list as of 0033, as 0021 lists them:
# (record table, table of its keywords relation, foreign key of that relation)
MAINTAINED_RECORD_TYPES = [('registry_datasetmetadatarecord', 'registry_datasetmetadatarecord_keywords', 'datasetmetadatarecord_id'), ('registry_servicemetadatarecord', 'registry_servicemetadatarecord_keywords', 'servicemetadatarecord_id'), ('registry_applicationmetadatarecord', 'registry_applicationmetadatarecord_keywords', 'applicationmetadatarecord_id')]

# the aggregate of 0021: the value every legacy object below and every
# pgtrigger object of registry/triggers.py writes
AGGREGATE = "(SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),\n                             '{{}}'::varchar(300)[])\n                 FROM {relation} AS relation\n                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id\n                WHERE relation.{foreign_key} = record.id\n                  AND btrim(keyword.keyword) <> '')"


def inside_sql_literal(statement):
    """The statement as it must appear inside a single quoted sql literal."""
    return statement.replace("'", "''")


# as in 0021 and 0024: inside the sync and keep functions the relation and its
# foreign key are only known at run time and passed through format()
TRIGGER_AGGREGATE = inside_sql_literal(
    AGGREGATE.format(relation="%2$I", foreign_key="%3$I"))


def legacy_sync_function():
    """The sync function of 0021."""
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
""".format(aggregate=TRIGGER_AGGREGATE)


def legacy_keep_function():
    """The guard function of 0024."""
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
""".format(aggregate=TRIGGER_AGGREGATE)


def legacy_rename_function():
    """The fan-out of 0021 as 0033 replaced it, knowing every maintained type."""
    updates = ""
    for record, relation, foreign_key in MAINTAINED_RECORD_TYPES:
        updates += """        UPDATE {record} AS record
           SET keywords_list = {aggregate};

""".format(record=record,
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


def legacy_objects():
    """Every legacy function and trigger, as the state of 0034 holds them."""
    create = (legacy_sync_function() + legacy_keep_function()
              + legacy_rename_function())
    for record, relation, foreign_key in MAINTAINED_RECORD_TYPES:
        create += """
CREATE TRIGGER {relation}_keywords_list_sync
    AFTER INSERT OR UPDATE OR DELETE ON {relation}
    FOR EACH ROW
    EXECUTE FUNCTION registry_sync_metadatarecord_keywords_list('{record}', '{foreign_key}');
""".format(relation=relation, record=record, foreign_key=foreign_key)
    for record, relation, foreign_key in MAINTAINED_RECORD_TYPES:
        create += """
CREATE TRIGGER {record}_keywords_list_keep
    BEFORE UPDATE ON {record}
    FOR EACH ROW
    EXECUTE FUNCTION registry_keep_metadatarecord_keywords_list('{relation}', '{foreign_key}');
""".format(record=record, relation=relation, foreign_key=foreign_key)
    create += """
CREATE TRIGGER registry_keyword_sync_to_metadatarecords
    AFTER UPDATE OF keyword ON registry_keyword
    FOR EACH ROW
    EXECUTE FUNCTION registry_sync_keyword_rename_to_metadatarecords();
"""
    return create


def legacy_drop():
    """The removal of every object 0021, 0024 and 0033 created."""
    drop = ""
    for _record, relation, _foreign_key in MAINTAINED_RECORD_TYPES:
        drop += ("DROP TRIGGER IF EXISTS %s ON %s;\n"
                 % (relation + "_keywords_list_sync", relation))
    for record, _relation, _foreign_key in MAINTAINED_RECORD_TYPES:
        drop += ("DROP TRIGGER IF EXISTS %s ON %s;\n"
                 % (record + "_keywords_list_keep", record))
    drop += ("DROP TRIGGER IF EXISTS registry_keyword_sync_to_metadatarecords"
             " ON registry_keyword;\n")
    drop += "DROP FUNCTION IF EXISTS registry_sync_metadatarecord_keywords_list();\n"
    drop += "DROP FUNCTION IF EXISTS registry_keep_metadatarecord_keywords_list();\n"
    drop += "DROP FUNCTION IF EXISTS registry_sync_keyword_rename_to_metadatarecords();\n"
    return drop


LEGACY_CREATE_SQL = legacy_objects()
LEGACY_DROP_SQL = legacy_drop()


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0034_remove_harvestedmetadatarelation_dm_record_or_sm_record_and_more'),
    ]

    operations = [
        # unmanaged model for the keywords relation of the records:
        # the state side of the existing table, the database side is
        # the untouched table of the auto-created through model
        migrations.CreateModel(
            name='DatasetMetadataRecordKeywordsLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('datasetmetadatarecord', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='d_keywords_link+', to='registry.datasetmetadatarecord')),
                ('keyword', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='d_keywords_link+', to='registry.keyword')),
            ],
            options={
                'db_table': 'registry_datasetmetadatarecord_keywords',
                'managed': False,
                'indexes': [],
                'constraints': [],
            },
        ),

        # unmanaged model for the keywords relation of the records:
        # the state side of the existing table, the database side is
        # the untouched table of the auto-created through model
        migrations.CreateModel(
            name='ServiceMetadataRecordKeywordsLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('servicemetadatarecord', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='s_keywords_link+', to='registry.servicemetadatarecord')),
                ('keyword', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='s_keywords_link+', to='registry.keyword')),
            ],
            options={
                'db_table': 'registry_servicemetadatarecord_keywords',
                'managed': False,
                'indexes': [],
                'constraints': [],
            },
        ),

        # unmanaged model for the keywords relation of the records:
        # the state side of the existing table, the database side is
        # the untouched table of the auto-created through model
        migrations.CreateModel(
            name='ApplicationMetadataRecordKeywordsLink',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('applicationmetadatarecord', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='a_keywords_link+', to='registry.applicationmetadatarecord')),
                ('keyword', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='a_keywords_link+', to='registry.keyword')),
            ],
            options={
                'db_table': 'registry_applicationmetadatarecord_keywords',
                'managed': False,
                'indexes': [],
                'constraints': [],
            },
        ),

        # the transfer: the legacy objects are dropped and the
        # pgtrigger objects of registry/triggers.py installed, statement
        # list by statement list, inside this migration's transaction
        migrations.RunSQL(
            LEGACY_DROP_SQL,
            reverse_sql=LEGACY_CREATE_SQL,
        ),

        pgtrigger.migrations.AddTrigger(
            model_name='applicationmetadatarecord',
            trigger=pgtrigger.compiler.Trigger(name='applicationmetadatarecord_keywords_list_keep', sql=pgtrigger.compiler.UpsertTriggerSql(declare='DECLARE maintained text[];', func="\n    -- the array belongs to the database, so a value which differs from the stored\n    -- one is not a change but a write which did not read the column: answered from\n    -- the relation, never from the write. A writer which carries the stored value\n    -- is the common case and is not asked for the aggregate.\n    IF NEW.keywords_list IS DISTINCT FROM OLD.keywords_list THEN\n        SELECT (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),\n                             '{}'::varchar(300)[])\n                 FROM registry_applicationmetadatarecord_keywords AS relation\n                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id\n                WHERE relation.applicationmetadatarecord_id = record.id\n                  AND btrim(keyword.keyword) <> '')\n          FROM registry_applicationmetadatarecord AS record\n         WHERE record.id = NEW.id\n          INTO maintained;\n\n        NEW.keywords_list := maintained;\n    END IF;\n\n    RETURN NEW;\n", hash='25e011f398d814d8619376261992cff9881333d1', operation='UPDATE', pgid='pgtrigger_applicationmetadatarecord_keywords_list_keep_514e9', table='registry_applicationmetadatarecord', when='BEFORE')),
        ),

        registry.triggers.AddKeywordsLinkTrigger(
            model_name='applicationmetadatarecordkeywordslink',
            trigger=pgtrigger.compiler.Trigger(name='applicationmetadatarecord_keywords_list_sync', sql=pgtrigger.compiler.UpsertTriggerSql(declare='DECLARE record_id uuid;', func="\n    -- the key is read through jsonb: which side of the relation the trigger\n    -- row is depends on the operation\n    SELECT (to_jsonb(CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END) ->> 'applicationmetadatarecord_id')::uuid\n      INTO record_id;\n\n    IF NOT FOUND OR record_id IS NULL THEN\n        RETURN NULL;\n    END IF;\n\n    UPDATE registry_applicationmetadatarecord AS record\n       SET keywords_list = (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),\n                             '{}'::varchar(300)[])\n                 FROM registry_applicationmetadatarecord_keywords AS relation\n                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id\n                WHERE relation.applicationmetadatarecord_id = record.id\n                  AND btrim(keyword.keyword) <> '')\n     WHERE record.id = record_id;\n\n    RETURN NULL;\n", hash='c1bf30d82c263773388db5cd4e22b9abb1cd3b69', operation='INSERT OR UPDATE OR DELETE', pgid='pgtrigger_applicationmetadatarecord_keywords_list_sync_be2e0', table='registry_applicationmetadatarecord_keywords', when='AFTER')),
        ),

        pgtrigger.migrations.AddTrigger(
            model_name='datasetmetadatarecord',
            trigger=pgtrigger.compiler.Trigger(name='datasetmetadatarecord_keywords_list_keep', sql=pgtrigger.compiler.UpsertTriggerSql(declare='DECLARE maintained text[];', func="\n    -- the array belongs to the database, so a value which differs from the stored\n    -- one is not a change but a write which did not read the column: answered from\n    -- the relation, never from the write. A writer which carries the stored value\n    -- is the common case and is not asked for the aggregate.\n    IF NEW.keywords_list IS DISTINCT FROM OLD.keywords_list THEN\n        SELECT (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),\n                             '{}'::varchar(300)[])\n                 FROM registry_datasetmetadatarecord_keywords AS relation\n                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id\n                WHERE relation.datasetmetadatarecord_id = record.id\n                  AND btrim(keyword.keyword) <> '')\n          FROM registry_datasetmetadatarecord AS record\n         WHERE record.id = NEW.id\n          INTO maintained;\n\n        NEW.keywords_list := maintained;\n    END IF;\n\n    RETURN NEW;\n", hash='2fa3f2ae45e5ecb31adc00796a125880a29ed750', operation='UPDATE', pgid='pgtrigger_datasetmetadatarecord_keywords_list_keep_55cae', table='registry_datasetmetadatarecord', when='BEFORE')),
        ),

        registry.triggers.AddKeywordsLinkTrigger(
            model_name='datasetmetadatarecordkeywordslink',
            trigger=pgtrigger.compiler.Trigger(name='datasetmetadatarecord_keywords_list_sync', sql=pgtrigger.compiler.UpsertTriggerSql(declare='DECLARE record_id uuid;', func="\n    -- the key is read through jsonb: which side of the relation the trigger\n    -- row is depends on the operation\n    SELECT (to_jsonb(CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END) ->> 'datasetmetadatarecord_id')::uuid\n      INTO record_id;\n\n    IF NOT FOUND OR record_id IS NULL THEN\n        RETURN NULL;\n    END IF;\n\n    UPDATE registry_datasetmetadatarecord AS record\n       SET keywords_list = (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),\n                             '{}'::varchar(300)[])\n                 FROM registry_datasetmetadatarecord_keywords AS relation\n                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id\n                WHERE relation.datasetmetadatarecord_id = record.id\n                  AND btrim(keyword.keyword) <> '')\n     WHERE record.id = record_id;\n\n    RETURN NULL;\n", hash='f0ae2bcb2ec02e3ebb6103eddc784f52793fc8d4', operation='INSERT OR UPDATE OR DELETE', pgid='pgtrigger_datasetmetadatarecord_keywords_list_sync_e37fb', table='registry_datasetmetadatarecord_keywords', when='AFTER')),
        ),

        pgtrigger.migrations.AddTrigger(
            model_name='keyword',
            trigger=pgtrigger.compiler.Trigger(name='keyword_sync_to_metadatarecords', sql=pgtrigger.compiler.UpsertTriggerSql(func="\n    IF OLD.keyword IS DISTINCT FROM NEW.keyword THEN\n        UPDATE registry_datasetmetadatarecord AS record\n           SET keywords_list = (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),\n                             '{}'::varchar(300)[])\n                 FROM registry_datasetmetadatarecord_keywords AS relation\n                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id\n                WHERE relation.datasetmetadatarecord_id = record.id\n                  AND btrim(keyword.keyword) <> '');\n\n        UPDATE registry_servicemetadatarecord AS record\n           SET keywords_list = (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),\n                             '{}'::varchar(300)[])\n                 FROM registry_servicemetadatarecord_keywords AS relation\n                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id\n                WHERE relation.servicemetadatarecord_id = record.id\n                  AND btrim(keyword.keyword) <> '');\n\n        UPDATE registry_applicationmetadatarecord AS record\n           SET keywords_list = (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),\n                             '{}'::varchar(300)[])\n                 FROM registry_applicationmetadatarecord_keywords AS relation\n                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id\n                WHERE relation.applicationmetadatarecord_id = record.id\n                  AND btrim(keyword.keyword) <> '');\n\n    END IF;\n\n    RETURN NULL;\n", hash='830a7efbb3f9e36f800690bbb8100e812b4d58e4', operation='UPDATE OF "keyword"', pgid='pgtrigger_keyword_sync_to_metadatarecords_e8557', table='registry_keyword', when='AFTER')),
        ),

        pgtrigger.migrations.AddTrigger(
            model_name='servicemetadatarecord',
            trigger=pgtrigger.compiler.Trigger(name='servicemetadatarecord_keywords_list_keep', sql=pgtrigger.compiler.UpsertTriggerSql(declare='DECLARE maintained text[];', func="\n    -- the array belongs to the database, so a value which differs from the stored\n    -- one is not a change but a write which did not read the column: answered from\n    -- the relation, never from the write. A writer which carries the stored value\n    -- is the common case and is not asked for the aggregate.\n    IF NEW.keywords_list IS DISTINCT FROM OLD.keywords_list THEN\n        SELECT (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),\n                             '{}'::varchar(300)[])\n                 FROM registry_servicemetadatarecord_keywords AS relation\n                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id\n                WHERE relation.servicemetadatarecord_id = record.id\n                  AND btrim(keyword.keyword) <> '')\n          FROM registry_servicemetadatarecord AS record\n         WHERE record.id = NEW.id\n          INTO maintained;\n\n        NEW.keywords_list := maintained;\n    END IF;\n\n    RETURN NEW;\n", hash='7a5a76ce6f8c7cfd020d82fee840dacf40b016c9', operation='UPDATE', pgid='pgtrigger_servicemetadatarecord_keywords_list_keep_83cbe', table='registry_servicemetadatarecord', when='BEFORE')),
        ),

        registry.triggers.AddKeywordsLinkTrigger(
            model_name='servicemetadatarecordkeywordslink',
            trigger=pgtrigger.compiler.Trigger(name='servicemetadatarecord_keywords_list_sync', sql=pgtrigger.compiler.UpsertTriggerSql(declare='DECLARE record_id uuid;', func="\n    -- the key is read through jsonb: which side of the relation the trigger\n    -- row is depends on the operation\n    SELECT (to_jsonb(CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END) ->> 'servicemetadatarecord_id')::uuid\n      INTO record_id;\n\n    IF NOT FOUND OR record_id IS NULL THEN\n        RETURN NULL;\n    END IF;\n\n    UPDATE registry_servicemetadatarecord AS record\n       SET keywords_list = (SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),\n                             '{}'::varchar(300)[])\n                 FROM registry_servicemetadatarecord_keywords AS relation\n                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id\n                WHERE relation.servicemetadatarecord_id = record.id\n                  AND btrim(keyword.keyword) <> '')\n     WHERE record.id = record_id;\n\n    RETURN NULL;\n", hash='118bc944e62db4a1f3483da62b43578845898936', operation='INSERT OR UPDATE OR DELETE', pgid='pgtrigger_servicemetadatarecord_keywords_list_sync_2317c', table='registry_servicemetadatarecord_keywords', when='AFTER')),
        ),
    ]
