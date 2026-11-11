"""The keyword maintenance of the metadata records as triggers of the database.

A record which is searchable by keyword needs the keywords *of the record row*:
aggregating the keywords relation is not expressible as a column expression, so
the ``keywords_list`` array of a record is kept in sync by the database. These
are the rules which ``0021``, ``0024`` and ``0033`` of the registry migrations
introduced by hand; django-pgtrigger owns them now, so they travel through the
migrations as declarative objects and their ``CREATE FUNCTION`` / ``CREATE
TRIGGER`` boilerplate is replaced by the transfer migration
``0039_the_keyword_maintenance_is_managed_by_pgtrigger`` (#1009). Importing this
module registers the triggers on their models -- ``registry.apps`` does that
when the app registry is ready, which is when the makemigrations autodetector
and the migrate command read them. There are three kinds:

``*_keywords_list_sync``
    one trigger on the keywords relation of every maintained record type. It
    answers every write of the relation -- the orm, a bulk ``.set()``, plain
    sql -- with the aggregate the relation says.

``*_keywords_list_keep``
    one trigger on every maintained record table. A write of a *record row*
    which brings an array it never read (a fixture, a built instance) gets the
    value of the relation instead; a writer which carries the stored value is
    answered without the aggregate. Being a BEFORE trigger is what lets the
    stored ``search_vector`` compute from the array which is really written.

``keyword_sync_to_metadatarecords``
    one trigger on the keyword itself. A rename is the one change which does
    not pass through a keywords relation, so it is fanned out over the records
    which hold the keyword. This is a set based update and meant to be rare:
    an administrative edit, not a harvesting path.

The sync triggers are registered on the explicit through models
``registry.models.metadata....KeywordsLink``. These managed models own the
existing keywords relation tables and expose their triggers to migrations.

Trigger objects in the database are named ``pgtrigger_<name>_<hash>``, not by
the legacy names -- the package manages its objects under that prefix and reads
them back with it. The *value* every trigger writes is the statement of
``0021`` verbatim, which is what makes the transfer a no-op for the data.
"""

from pgtrigger import (After, Before, Delete, Insert, Trigger, Update,
                       UpdateOf, register)
from pgtrigger.migrations import AddTrigger

from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, Keyword,
                                      ServiceMetadataRecord)


METADATA_RECORD_MODELS = (
    DatasetMetadataRecord, ServiceMetadataRecord, ApplicationMetadataRecord,
)


class AddKeywordsLinkTrigger(AddTrigger):
    """Historical operation used by the unmanaged link models in migration 0039.

    The link models in that migration were unmanaged: their tables belonged to
    the automatic keywords relations. Django skipped their database operations,
    so this operation checked only the database vendor to install the triggers
    (#1009). Its reverse uses the same check.
    Keep this class for applying and reversing that migration; the managed
    through models now use the ordinary pgtrigger operations.
    """

    def allow_migrate_model_trigger(self, schema_editor, model):
        return schema_editor.connection.vendor == "postgresql"


# the aggregate answering the keywords of one record -- the statement of
# 0021 with the one thing 0035 answered differently: the empty array carries
# the element type the columns have since 0028, so COALESCE has one type to
# agree on and nothing is re-cast on the way into the widened column (#1075).
# pgtrigger keeps storing what the legacy triggers stored.
AGGREGATE = """(SELECT COALESCE(array_agg(DISTINCT keyword.keyword ORDER BY keyword.keyword),
                             '{{}}'::text[])
                 FROM {relation} AS relation
                 JOIN registry_keyword AS keyword ON keyword.id = relation.keyword_id
                WHERE relation.{foreign_key} = record.id
                  AND btrim(keyword.keyword) <> '')"""


class SyncKeywordsList(Trigger):
    """The trigger of ``0021``: every write of a keywords relation re-answers
    the array of the record the relation row points at."""

    when = After
    operation = Insert | Update | Delete
    declare = [("record_id", "uuid")]

    def get_func(self, model):
        record_field = next(field for field in model._meta.fields
                            if field.is_relation
                            and field.related_model._meta.label_lower != Keyword._meta.label_lower)
        return """
    -- the key is read through jsonb: which side of the relation the trigger
    -- row is depends on the operation
    SELECT (to_jsonb(CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END) ->> '{foreign_key}')::uuid
      INTO record_id;

    IF NOT FOUND OR record_id IS NULL THEN
        RETURN NULL;
    END IF;

    UPDATE {record} AS record
       SET keywords_list = {aggregate}
     WHERE record.id = record_id;

    RETURN NULL;
""".format(
            foreign_key=record_field.column,
            record=record_field.related_model._meta.db_table,
            aggregate=AGGREGATE.format(
                relation=model._meta.db_table,
                foreign_key=record_field.column))


class KeepKeywordsList(Trigger):
    """The guard of ``0024``: a write of a record row which brings an array it
    never read gets the value of the relation instead."""

    when = Before
    operation = Update
    declare = [("maintained", "text[]")]

    def get_func(self, model):
        keywords = model._meta.get_field("keywords")
        return """
    -- the array belongs to the database, so a value which differs from the stored
    -- one is not a change but a write which did not read the column: answered from
    -- the relation, never from the write. A writer which carries the stored value
    -- is the common case and is not asked for the aggregate.
    IF NEW.keywords_list IS DISTINCT FROM OLD.keywords_list THEN
        SELECT {aggregate}
          FROM {record} AS record
         WHERE record.id = NEW.id
          INTO maintained;

        NEW.keywords_list := maintained;
    END IF;

    RETURN NEW;
""".format(
            record=model._meta.db_table,
            aggregate=AGGREGATE.format(
                relation=keywords.remote_field.through._meta.db_table,
                foreign_key=keywords.m2m_column_name()))


class SyncKeywordRenameToMetadatarecords(Trigger):
    """The fan-out of ``0021``, knowing the three record types of ``0033``: a
    rename of a keyword is the one change which does not pass through a
    keywords relation."""

    name = "keyword_sync_to_metadatarecords"
    when = After
    operation = UpdateOf("keyword")

    def get_func(self, model):
        updates = ""
        for record in METADATA_RECORD_MODELS:
            keywords = record._meta.get_field("keywords")
            updates += """        UPDATE {record} AS record
           SET keywords_list = {aggregate};

""".format(
                record=record._meta.db_table,
                aggregate=AGGREGATE.format(
                    relation=keywords.remote_field.through._meta.db_table,
                    foreign_key=keywords.m2m_column_name()))

        return """
    IF OLD.keyword IS DISTINCT FROM NEW.keyword THEN
{updates}    END IF;

    RETURN NULL;
""".format(updates=updates)


# Register relation triggers on the through models and the remaining triggers
# on the record and keyword models themselves.
for record_model in METADATA_RECORD_MODELS:
    register(SyncKeywordsList(
        name=f"{record_model._meta.model_name}_keywords_list_sync"))(
            record_model.keywords.through)
    register(KeepKeywordsList(
        name=f"{record_model._meta.model_name}_keywords_list_keep"))(record_model)

register(SyncKeywordRenameToMetadatarecords())(Keyword)
