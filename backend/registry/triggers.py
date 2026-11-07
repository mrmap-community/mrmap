"""The keyword maintenance of the metadata records as triggers of the database.

A record which is searchable by keyword needs the keywords *of the record row*:
aggregating the keywords relation is not expressible as a column expression, so
the ``keywords_list`` array of a record is kept in sync by the database. These
are the rules which ``0021``, ``0024`` and ``0033`` of the registry migrations
introduced by hand; django-pgtrigger owns them now, so they travel through the
migrations as declarative objects and their ``CREATE FUNCTION`` / ``CREATE
TRIGGER`` boilerplate is replaced by the transfer migration
``0038_the_keyword_maintenance_is_managed_by_pgtrigger`` (#1009). Importing this
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

The sync triggers are registered on the unmanaged models
``registry.models.metadata....KeywordsLink``: a trigger is declared on a model,
and the auto-created through model of an ``ManyToManyField`` never enters the
migration state, so the autodetector cannot see a trigger on it (#1009).

Trigger objects in the database are named ``pgtrigger_<name>_<hash>``, not by
the legacy names -- the package manages its objects under that prefix and reads
them back with it. The *value* every trigger writes is the statement of
``0021`` verbatim, which is what makes the transfer a no-op for the data.
"""

from pgtrigger import (After, Before, Delete, Insert, Trigger, Update,
                       UpdateOf, register)
from pgtrigger.migrations import AddTrigger

from registry.models.metadata import (ApplicationMetadataRecord,
                                      ApplicationMetadataRecordKeywordsLink,
                                      DatasetMetadataRecord,
                                      DatasetMetadataRecordKeywordsLink,
                                      Keyword, ServiceMetadataRecord,
                                      ServiceMetadataRecordKeywordsLink)


class AddKeywordsLinkTrigger(AddTrigger):
    """The AddTrigger of the keywords relation triggers.

    Django's migrate skips every operation of an unmanaged model, and the link
    models carrying the sync triggers are unmanaged on purpose -- their table
    belongs to the keywords field, not to them. Their trigger must nevertheless
    reach the database from the migration, so this operation asks only the
    vendor, exactly as its parent does for a managed model (#1009). The reverse
    of the operation -- the trigger removal -- goes through the same check.
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

    # set by the subclasses: (record table, relation table, foreign key) as
    # the triples of MAINTAINED_RECORD_TYPES in 0021 name them
    RECORD_TABLE = ""
    RELATION_TABLE = ""
    FOREIGN_KEY = ""

    def get_func(self, model):
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
            foreign_key=self.FOREIGN_KEY,
            record=self.RECORD_TABLE,
            aggregate=AGGREGATE.format(
                relation=self.RELATION_TABLE,
                foreign_key=self.FOREIGN_KEY))


class DatasetMetadataRecordKeywordsListSync(SyncKeywordsList):
    name = "datasetmetadatarecord_keywords_list_sync"
    RECORD_TABLE = "registry_datasetmetadatarecord"
    RELATION_TABLE = "registry_datasetmetadatarecord_keywords"
    FOREIGN_KEY = "datasetmetadatarecord_id"


class ServiceMetadataRecordKeywordsListSync(SyncKeywordsList):
    name = "servicemetadatarecord_keywords_list_sync"
    RECORD_TABLE = "registry_servicemetadatarecord"
    RELATION_TABLE = "registry_servicemetadatarecord_keywords"
    FOREIGN_KEY = "servicemetadatarecord_id"


class ApplicationMetadataRecordKeywordsListSync(SyncKeywordsList):
    name = "applicationmetadatarecord_keywords_list_sync"
    RECORD_TABLE = "registry_applicationmetadatarecord"
    RELATION_TABLE = "registry_applicationmetadatarecord_keywords"
    FOREIGN_KEY = "applicationmetadatarecord_id"


class KeepKeywordsList(Trigger):
    """The guard of ``0024``: a write of a record row which brings an array it
    never read gets the value of the relation instead."""

    when = Before
    operation = Update
    declare = [("maintained", "text[]")]

    # set by the subclasses, as in SyncKeywordsList
    RECORD_TABLE = ""
    RELATION_TABLE = ""
    FOREIGN_KEY = ""

    def get_func(self, model):
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
            record=self.RECORD_TABLE,
            aggregate=AGGREGATE.format(
                relation=self.RELATION_TABLE,
                foreign_key=self.FOREIGN_KEY))


class DatasetMetadataRecordKeywordsListKeep(KeepKeywordsList):
    name = "datasetmetadatarecord_keywords_list_keep"
    RECORD_TABLE = "registry_datasetmetadatarecord"
    RELATION_TABLE = "registry_datasetmetadatarecord_keywords"
    FOREIGN_KEY = "datasetmetadatarecord_id"


class ServiceMetadataRecordKeywordsListKeep(KeepKeywordsList):
    name = "servicemetadatarecord_keywords_list_keep"
    RECORD_TABLE = "registry_servicemetadatarecord"
    RELATION_TABLE = "registry_servicemetadatarecord_keywords"
    FOREIGN_KEY = "servicemetadatarecord_id"


class ApplicationMetadataRecordKeywordsListKeep(KeepKeywordsList):
    name = "applicationmetadatarecord_keywords_list_keep"
    RECORD_TABLE = "registry_applicationmetadatarecord"
    RELATION_TABLE = "registry_applicationmetadatarecord_keywords"
    FOREIGN_KEY = "applicationmetadatarecord_id"


class SyncKeywordRenameToMetadatarecords(Trigger):
    """The fan-out of ``0021``, knowing the three record types of ``0033``: a
    rename of a keyword is the one change which does not pass through a
    keywords relation."""

    name = "keyword_sync_to_metadatarecords"
    when = After
    operation = UpdateOf("keyword")

    # the record types a rename reaches, as 0033 lists them
    MAINTAINED_RECORD_TYPES = [
        ("registry_datasetmetadatarecord",
         "registry_datasetmetadatarecord_keywords", "datasetmetadatarecord_id"),
        ("registry_servicemetadatarecord",
         "registry_servicemetadatarecord_keywords", "servicemetadatarecord_id"),
        ("registry_applicationmetadatarecord",
         "registry_applicationmetadatarecord_keywords",
         "applicationmetadatarecord_id"),
    ]

    def get_func(self, model):
        updates = ""
        for record, relation, foreign_key in self.MAINTAINED_RECORD_TYPES:
            updates += """        UPDATE {record} AS record
           SET keywords_list = {aggregate};

""".format(
                record=record,
                aggregate=AGGREGATE.format(
                    relation=relation, foreign_key=foreign_key))

        return """
    IF OLD.keyword IS DISTINCT FROM NEW.keyword THEN
{updates}    END IF;

    RETURN NULL;
""".format(updates=updates)


# the registration: on the relation tables it is the unmanaged link models
# which carry it (see the module docstring), on the record tables and the
# keyword the maintained models themselves.
register(DatasetMetadataRecordKeywordsListSync())(
    DatasetMetadataRecordKeywordsLink)
register(ServiceMetadataRecordKeywordsListSync())(
    ServiceMetadataRecordKeywordsLink)
register(ApplicationMetadataRecordKeywordsListSync())(
    ApplicationMetadataRecordKeywordsLink)

register(DatasetMetadataRecordKeywordsListKeep())(DatasetMetadataRecord)
register(ServiceMetadataRecordKeywordsListKeep())(ServiceMetadataRecord)
register(ApplicationMetadataRecordKeywordsListKeep())(
    ApplicationMetadataRecord)

register(SyncKeywordRenameToMetadatarecords())(Keyword)
