"""The delta size of a history row, computed by the database.

Which fields a revision touched is answered in the trigger, not in python: the
history tables are written from several processes, and only the row which
precedes this one knows what changed. ``bulk_create_with_history()`` -- the
path the harvesting configs select -- reaches neither ``save()`` nor a signal,
so a hook could leave the column wrong and nothing would notice.

The functions and the triggers are hand-written sql, because Django has no way
to declare a trigger whose comparison column list follows the model. They are
therefore carried here verbatim, and they are generated rather than typed: the
statements are what the database which the previous chain had built reports
about itself, so this is what a deployment runs today, including the changes
later revisions had made to them. Reproduced with these two queries::

    select pg_get_functiondef(p.oid)
      from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname like 'registry_delta_size_%'
     order by p.proname;

    select pg_get_triggerdef(t.oid)
      from pg_trigger t
      join pg_class c on c.oid = t.tgrelid
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and not t.tgisinternal
       and t.tgname like 'registry_historical%_delta_size'
     order by t.tgname;

Ordering by name is what makes the generated file reproducible.

The functions are ``CREATE OR REPLACE``, the triggers are preceded by a
``DROP TRIGGER IF EXISTS``. Both so that running this statement again is
possible: ``CREATE TRIGGER`` alone fails where the trigger already exists, and
an instance of the previous chain reaches it that way -- ``migrate
--fake-initial`` skips a migration whose tables all exist, and a RunSQL node
creates no tables, so the statement runs where the triggers are already there.
"""

from django.db import migrations


CREATE_SQL = [
    r"""CREATE OR REPLACE FUNCTION public.registry_delta_size_historicalapplicationmetadatarecord()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    -- the row this one precedes, if the record has one at all
    previous RECORD;
BEGIN
    SELECT written.access_constraints, written.abstract, written.application_contact_id, written.bounding_geometry, written.charset, written.code, written.code_space, written.fees, written.inspire_interoperability, written.is_searchable, written.licence_id, written.license_source_note, written.metadata_contact_id, written.profile_id, written.title, written.update_frequency_code, written.use_limitation
      INTO previous
      FROM registry_historicalapplicationmetadatarecord AS written
     WHERE written.id = NEW.id
                   AND (written.history_date, written.history_id)
                       < (NEW.history_date, NEW.history_id)
     ORDER BY written.history_date DESC, written.history_id DESC
     LIMIT 1;

    IF NOT FOUND THEN
        -- nothing to compare with, which is not the same as nothing changed
        NEW.delta_size := NULL;
        RETURN NEW;
    END IF;

    NEW.delta_size := (previous.access_constraints IS DISTINCT FROM NEW.access_constraints)::int
                    + (previous.abstract IS DISTINCT FROM NEW.abstract)::int
                    + (previous.application_contact_id IS DISTINCT FROM NEW.application_contact_id)::int
                    + (previous.bounding_geometry IS DISTINCT FROM NEW.bounding_geometry)::int
                    + (previous.charset IS DISTINCT FROM NEW.charset)::int
                    + (previous.code IS DISTINCT FROM NEW.code)::int
                    + (previous.code_space IS DISTINCT FROM NEW.code_space)::int
                    + (previous.fees IS DISTINCT FROM NEW.fees)::int
                    + (previous.inspire_interoperability IS DISTINCT FROM NEW.inspire_interoperability)::int
                    + (previous.is_searchable IS DISTINCT FROM NEW.is_searchable)::int
                    + (previous.licence_id IS DISTINCT FROM NEW.licence_id)::int
                    + (previous.license_source_note IS DISTINCT FROM NEW.license_source_note)::int
                    + (previous.metadata_contact_id IS DISTINCT FROM NEW.metadata_contact_id)::int
                    + (previous.profile_id IS DISTINCT FROM NEW.profile_id)::int
                    + (previous.title IS DISTINCT FROM NEW.title)::int
                    + (previous.update_frequency_code IS DISTINCT FROM NEW.update_frequency_code)::int
                    + (previous.use_limitation IS DISTINCT FROM NEW.use_limitation)::int;
    RETURN NEW;
END;
$function$;""",
    r"""CREATE OR REPLACE FUNCTION public.registry_delta_size_historicalcatalogueservice()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    -- the row this one precedes, if the record has one at all
    previous RECORD;
BEGIN
    SELECT written.access_constraints, written.abstract, written.fees, written.is_active, written.is_searchable, written.licence_id, written.license_source_note, written.max_step_size, written.metadata_contact_id, written.service_contact_id, written.title, written.use_limitation
      INTO previous
      FROM registry_historicalcatalogueservice AS written
     WHERE written.id = NEW.id
                   AND (written.history_date, written.history_id)
                       < (NEW.history_date, NEW.history_id)
     ORDER BY written.history_date DESC, written.history_id DESC
     LIMIT 1;

    IF NOT FOUND THEN
        -- nothing to compare with, which is not the same as nothing changed
        NEW.delta_size := NULL;
        RETURN NEW;
    END IF;

    NEW.delta_size := (previous.access_constraints IS DISTINCT FROM NEW.access_constraints)::int
                    + (previous.abstract IS DISTINCT FROM NEW.abstract)::int
                    + (previous.fees IS DISTINCT FROM NEW.fees)::int
                    + (previous.is_active IS DISTINCT FROM NEW.is_active)::int
                    + (previous.is_searchable IS DISTINCT FROM NEW.is_searchable)::int
                    + (previous.licence_id IS DISTINCT FROM NEW.licence_id)::int
                    + (previous.license_source_note IS DISTINCT FROM NEW.license_source_note)::int
                    + (previous.max_step_size IS DISTINCT FROM NEW.max_step_size)::int
                    + (previous.metadata_contact_id IS DISTINCT FROM NEW.metadata_contact_id)::int
                    + (previous.service_contact_id IS DISTINCT FROM NEW.service_contact_id)::int
                    + (previous.title IS DISTINCT FROM NEW.title)::int
                    + (previous.use_limitation IS DISTINCT FROM NEW.use_limitation)::int;
    RETURN NEW;
END;
$function$;""",
    r"""CREATE OR REPLACE FUNCTION public.registry_delta_size_historicaldatasetmetadatarecord()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    -- the row this one precedes, if the record has one at all
    previous RECORD;
BEGIN
    SELECT written.access_constraints, written.abstract, written.bounding_geometry, written.charset, written.code, written.code_space, written.dataset_contact_id, written.fees, written.format, written.inspire_interoperability, written.inspire_top_consistence, written.is_searchable, written.licence_id, written.license_source_note, written.lineage_statement, written.metadata_contact_id, written.preview_image, written.profile_id, written.title, written.update_frequency_code, written.use_limitation
      INTO previous
      FROM registry_historicaldatasetmetadatarecord AS written
     WHERE written.id = NEW.id
                   AND (written.history_date, written.history_id)
                       < (NEW.history_date, NEW.history_id)
     ORDER BY written.history_date DESC, written.history_id DESC
     LIMIT 1;

    IF NOT FOUND THEN
        -- nothing to compare with, which is not the same as nothing changed
        NEW.delta_size := NULL;
        RETURN NEW;
    END IF;

    NEW.delta_size := (previous.access_constraints IS DISTINCT FROM NEW.access_constraints)::int
                    + (previous.abstract IS DISTINCT FROM NEW.abstract)::int
                    + (previous.bounding_geometry IS DISTINCT FROM NEW.bounding_geometry)::int
                    + (previous.charset IS DISTINCT FROM NEW.charset)::int
                    + (previous.code IS DISTINCT FROM NEW.code)::int
                    + (previous.code_space IS DISTINCT FROM NEW.code_space)::int
                    + (previous.dataset_contact_id IS DISTINCT FROM NEW.dataset_contact_id)::int
                    + (previous.fees IS DISTINCT FROM NEW.fees)::int
                    + (previous.format IS DISTINCT FROM NEW.format)::int
                    + (previous.inspire_interoperability IS DISTINCT FROM NEW.inspire_interoperability)::int
                    + (previous.inspire_top_consistence IS DISTINCT FROM NEW.inspire_top_consistence)::int
                    + (previous.is_searchable IS DISTINCT FROM NEW.is_searchable)::int
                    + (previous.licence_id IS DISTINCT FROM NEW.licence_id)::int
                    + (previous.license_source_note IS DISTINCT FROM NEW.license_source_note)::int
                    + (previous.lineage_statement IS DISTINCT FROM NEW.lineage_statement)::int
                    + (previous.metadata_contact_id IS DISTINCT FROM NEW.metadata_contact_id)::int
                    + (previous.preview_image IS DISTINCT FROM NEW.preview_image)::int
                    + (previous.profile_id IS DISTINCT FROM NEW.profile_id)::int
                    + (previous.title IS DISTINCT FROM NEW.title)::int
                    + (previous.update_frequency_code IS DISTINCT FROM NEW.update_frequency_code)::int
                    + (previous.use_limitation IS DISTINCT FROM NEW.use_limitation)::int;
    RETURN NEW;
END;
$function$;""",
    r"""CREATE OR REPLACE FUNCTION public.registry_delta_size_historicalfeaturetype()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    -- the row this one precedes, if the record has one at all
    previous RECORD;
BEGIN
    SELECT written.abstract, written.default_reference_system_id, written.describe_feature_type_document, written.is_active, written.is_searchable, written.title
      INTO previous
      FROM registry_historicalfeaturetype AS written
     WHERE written.id = NEW.id
                   AND (written.history_date, written.history_id)
                       < (NEW.history_date, NEW.history_id)
     ORDER BY written.history_date DESC, written.history_id DESC
     LIMIT 1;

    IF NOT FOUND THEN
        -- nothing to compare with, which is not the same as nothing changed
        NEW.delta_size := NULL;
        RETURN NEW;
    END IF;

    NEW.delta_size := (previous.abstract IS DISTINCT FROM NEW.abstract)::int
                    + (previous.default_reference_system_id IS DISTINCT FROM NEW.default_reference_system_id)::int
                    + (previous.describe_feature_type_document IS DISTINCT FROM NEW.describe_feature_type_document)::int
                    + (previous.is_active IS DISTINCT FROM NEW.is_active)::int
                    + (previous.is_searchable IS DISTINCT FROM NEW.is_searchable)::int
                    + (previous.title IS DISTINCT FROM NEW.title)::int;
    RETURN NEW;
END;
$function$;""",
    r"""CREATE OR REPLACE FUNCTION public.registry_delta_size_historicallayer()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    -- the row this one precedes, if the record has one at all
    previous RECORD;
BEGIN
    SELECT written.abstract, written.is_active, written.is_searchable, written.preview_image, written.title
      INTO previous
      FROM registry_historicallayer AS written
     WHERE written.id = NEW.id
                   AND (written.history_date, written.history_id)
                       < (NEW.history_date, NEW.history_id)
     ORDER BY written.history_date DESC, written.history_id DESC
     LIMIT 1;

    IF NOT FOUND THEN
        -- nothing to compare with, which is not the same as nothing changed
        NEW.delta_size := NULL;
        RETURN NEW;
    END IF;

    NEW.delta_size := (previous.abstract IS DISTINCT FROM NEW.abstract)::int
                    + (previous.is_active IS DISTINCT FROM NEW.is_active)::int
                    + (previous.is_searchable IS DISTINCT FROM NEW.is_searchable)::int
                    + (previous.preview_image IS DISTINCT FROM NEW.preview_image)::int
                    + (previous.title IS DISTINCT FROM NEW.title)::int;
    RETURN NEW;
END;
$function$;""",
    r"""CREATE OR REPLACE FUNCTION public.registry_delta_size_historicalservicemetadatarecord()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    -- the row this one precedes, if the record has one at all
    previous RECORD;
BEGIN
    SELECT written.access_constraints, written.abstract, written.bounding_geometry, written.charset, written.code, written.code_space, written.fees, written.inspire_interoperability, written.is_searchable, written.licence_id, written.license_source_note, written.metadata_contact_id, written.profile_id, written.title, written.use_limitation
      INTO previous
      FROM registry_historicalservicemetadatarecord AS written
     WHERE written.id = NEW.id
                   AND (written.history_date, written.history_id)
                       < (NEW.history_date, NEW.history_id)
     ORDER BY written.history_date DESC, written.history_id DESC
     LIMIT 1;

    IF NOT FOUND THEN
        -- nothing to compare with, which is not the same as nothing changed
        NEW.delta_size := NULL;
        RETURN NEW;
    END IF;

    NEW.delta_size := (previous.access_constraints IS DISTINCT FROM NEW.access_constraints)::int
                    + (previous.abstract IS DISTINCT FROM NEW.abstract)::int
                    + (previous.bounding_geometry IS DISTINCT FROM NEW.bounding_geometry)::int
                    + (previous.charset IS DISTINCT FROM NEW.charset)::int
                    + (previous.code IS DISTINCT FROM NEW.code)::int
                    + (previous.code_space IS DISTINCT FROM NEW.code_space)::int
                    + (previous.fees IS DISTINCT FROM NEW.fees)::int
                    + (previous.inspire_interoperability IS DISTINCT FROM NEW.inspire_interoperability)::int
                    + (previous.is_searchable IS DISTINCT FROM NEW.is_searchable)::int
                    + (previous.licence_id IS DISTINCT FROM NEW.licence_id)::int
                    + (previous.license_source_note IS DISTINCT FROM NEW.license_source_note)::int
                    + (previous.metadata_contact_id IS DISTINCT FROM NEW.metadata_contact_id)::int
                    + (previous.profile_id IS DISTINCT FROM NEW.profile_id)::int
                    + (previous.title IS DISTINCT FROM NEW.title)::int
                    + (previous.use_limitation IS DISTINCT FROM NEW.use_limitation)::int;
    RETURN NEW;
END;
$function$;""",
    r"""CREATE OR REPLACE FUNCTION public.registry_delta_size_historicalwebfeatureservice()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    -- the row this one precedes, if the record has one at all
    previous RECORD;
BEGIN
    SELECT written.access_constraints, written.abstract, written.fees, written.is_active, written.is_searchable, written.licence_id, written.license_source_note, written.metadata_contact_id, written.service_contact_id, written.title, written.use_limitation
      INTO previous
      FROM registry_historicalwebfeatureservice AS written
     WHERE written.id = NEW.id
                   AND (written.history_date, written.history_id)
                       < (NEW.history_date, NEW.history_id)
     ORDER BY written.history_date DESC, written.history_id DESC
     LIMIT 1;

    IF NOT FOUND THEN
        -- nothing to compare with, which is not the same as nothing changed
        NEW.delta_size := NULL;
        RETURN NEW;
    END IF;

    NEW.delta_size := (previous.access_constraints IS DISTINCT FROM NEW.access_constraints)::int
                    + (previous.abstract IS DISTINCT FROM NEW.abstract)::int
                    + (previous.fees IS DISTINCT FROM NEW.fees)::int
                    + (previous.is_active IS DISTINCT FROM NEW.is_active)::int
                    + (previous.is_searchable IS DISTINCT FROM NEW.is_searchable)::int
                    + (previous.licence_id IS DISTINCT FROM NEW.licence_id)::int
                    + (previous.license_source_note IS DISTINCT FROM NEW.license_source_note)::int
                    + (previous.metadata_contact_id IS DISTINCT FROM NEW.metadata_contact_id)::int
                    + (previous.service_contact_id IS DISTINCT FROM NEW.service_contact_id)::int
                    + (previous.title IS DISTINCT FROM NEW.title)::int
                    + (previous.use_limitation IS DISTINCT FROM NEW.use_limitation)::int;
    RETURN NEW;
END;
$function$;""",
    r"""CREATE OR REPLACE FUNCTION public.registry_delta_size_historicalwebmapservice()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
DECLARE
    -- the row this one precedes, if the record has one at all
    previous RECORD;
BEGIN
    SELECT written.access_constraints, written.abstract, written.fees, written.is_active, written.is_searchable, written.licence_id, written.license_source_note, written.metadata_contact_id, written.service_contact_id, written.title, written.use_limitation
      INTO previous
      FROM registry_historicalwebmapservice AS written
     WHERE written.id = NEW.id
                   AND (written.history_date, written.history_id)
                       < (NEW.history_date, NEW.history_id)
     ORDER BY written.history_date DESC, written.history_id DESC
     LIMIT 1;

    IF NOT FOUND THEN
        -- nothing to compare with, which is not the same as nothing changed
        NEW.delta_size := NULL;
        RETURN NEW;
    END IF;

    NEW.delta_size := (previous.access_constraints IS DISTINCT FROM NEW.access_constraints)::int
                    + (previous.abstract IS DISTINCT FROM NEW.abstract)::int
                    + (previous.fees IS DISTINCT FROM NEW.fees)::int
                    + (previous.is_active IS DISTINCT FROM NEW.is_active)::int
                    + (previous.is_searchable IS DISTINCT FROM NEW.is_searchable)::int
                    + (previous.licence_id IS DISTINCT FROM NEW.licence_id)::int
                    + (previous.license_source_note IS DISTINCT FROM NEW.license_source_note)::int
                    + (previous.metadata_contact_id IS DISTINCT FROM NEW.metadata_contact_id)::int
                    + (previous.service_contact_id IS DISTINCT FROM NEW.service_contact_id)::int
                    + (previous.title IS DISTINCT FROM NEW.title)::int
                    + (previous.use_limitation IS DISTINCT FROM NEW.use_limitation)::int;
    RETURN NEW;
END;
$function$;""",
    r"""DROP TRIGGER IF EXISTS registry_historicalapplicationmetadatarecord_delta_size ON registry_historicalapplicationmetadatarecord;""",
    r"""CREATE TRIGGER registry_historicalapplicationmetadatarecord_delta_size BEFORE INSERT OR UPDATE OF access_constraints, abstract, application_contact_id, bounding_geometry, charset, code, code_space, fees, inspire_interoperability, is_searchable, licence_id, license_source_note, metadata_contact_id, profile_id, title, update_frequency_code, use_limitation, delta_size ON public.registry_historicalapplicationmetadatarecord FOR EACH ROW EXECUTE FUNCTION registry_delta_size_historicalapplicationmetadatarecord();""",
    r"""DROP TRIGGER IF EXISTS registry_historicalcatalogueservice_delta_size ON registry_historicalcatalogueservice;""",
    r"""CREATE TRIGGER registry_historicalcatalogueservice_delta_size BEFORE INSERT OR UPDATE OF access_constraints, abstract, fees, is_active, is_searchable, licence_id, license_source_note, max_step_size, metadata_contact_id, service_contact_id, title, use_limitation, delta_size ON public.registry_historicalcatalogueservice FOR EACH ROW EXECUTE FUNCTION registry_delta_size_historicalcatalogueservice();""",
    r"""DROP TRIGGER IF EXISTS registry_historicaldatasetmetadatarecord_delta_size ON registry_historicaldatasetmetadatarecord;""",
    r"""CREATE TRIGGER registry_historicaldatasetmetadatarecord_delta_size BEFORE INSERT OR UPDATE OF access_constraints, abstract, bounding_geometry, charset, code, code_space, dataset_contact_id, fees, format, inspire_interoperability, inspire_top_consistence, is_searchable, licence_id, license_source_note, lineage_statement, metadata_contact_id, preview_image, profile_id, title, update_frequency_code, use_limitation, delta_size ON public.registry_historicaldatasetmetadatarecord FOR EACH ROW EXECUTE FUNCTION registry_delta_size_historicaldatasetmetadatarecord();""",
    r"""DROP TRIGGER IF EXISTS registry_historicalfeaturetype_delta_size ON registry_historicalfeaturetype;""",
    r"""CREATE TRIGGER registry_historicalfeaturetype_delta_size BEFORE INSERT OR UPDATE OF abstract, default_reference_system_id, describe_feature_type_document, is_active, is_searchable, title, delta_size ON public.registry_historicalfeaturetype FOR EACH ROW EXECUTE FUNCTION registry_delta_size_historicalfeaturetype();""",
    r"""DROP TRIGGER IF EXISTS registry_historicallayer_delta_size ON registry_historicallayer;""",
    r"""CREATE TRIGGER registry_historicallayer_delta_size BEFORE INSERT OR UPDATE OF abstract, is_active, is_searchable, preview_image, title, delta_size ON public.registry_historicallayer FOR EACH ROW EXECUTE FUNCTION registry_delta_size_historicallayer();""",
    r"""DROP TRIGGER IF EXISTS registry_historicalservicemetadatarecord_delta_size ON registry_historicalservicemetadatarecord;""",
    r"""CREATE TRIGGER registry_historicalservicemetadatarecord_delta_size BEFORE INSERT OR UPDATE OF access_constraints, abstract, bounding_geometry, charset, code, code_space, fees, inspire_interoperability, is_searchable, licence_id, license_source_note, metadata_contact_id, profile_id, title, use_limitation, delta_size ON public.registry_historicalservicemetadatarecord FOR EACH ROW EXECUTE FUNCTION registry_delta_size_historicalservicemetadatarecord();""",
    r"""DROP TRIGGER IF EXISTS registry_historicalwebfeatureservice_delta_size ON registry_historicalwebfeatureservice;""",
    r"""CREATE TRIGGER registry_historicalwebfeatureservice_delta_size BEFORE INSERT OR UPDATE OF access_constraints, abstract, fees, is_active, is_searchable, licence_id, license_source_note, metadata_contact_id, service_contact_id, title, use_limitation, delta_size ON public.registry_historicalwebfeatureservice FOR EACH ROW EXECUTE FUNCTION registry_delta_size_historicalwebfeatureservice();""",
    r"""DROP TRIGGER IF EXISTS registry_historicalwebmapservice_delta_size ON registry_historicalwebmapservice;""",
    r"""CREATE TRIGGER registry_historicalwebmapservice_delta_size BEFORE INSERT OR UPDATE OF access_constraints, abstract, fees, is_active, is_searchable, licence_id, license_source_note, metadata_contact_id, service_contact_id, title, use_limitation, delta_size ON public.registry_historicalwebmapservice FOR EACH ROW EXECUTE FUNCTION registry_delta_size_historicalwebmapservice();""",
]

DROP_SQL = [
    r"""DROP TRIGGER IF EXISTS registry_historicalapplicationmetadatarecord_delta_size ON registry_historicalapplicationmetadatarecord;""",
    r"""DROP TRIGGER IF EXISTS registry_historicalcatalogueservice_delta_size ON registry_historicalcatalogueservice;""",
    r"""DROP TRIGGER IF EXISTS registry_historicaldatasetmetadatarecord_delta_size ON registry_historicaldatasetmetadatarecord;""",
    r"""DROP TRIGGER IF EXISTS registry_historicalfeaturetype_delta_size ON registry_historicalfeaturetype;""",
    r"""DROP TRIGGER IF EXISTS registry_historicallayer_delta_size ON registry_historicallayer;""",
    r"""DROP TRIGGER IF EXISTS registry_historicalservicemetadatarecord_delta_size ON registry_historicalservicemetadatarecord;""",
    r"""DROP TRIGGER IF EXISTS registry_historicalwebfeatureservice_delta_size ON registry_historicalwebfeatureservice;""",
    r"""DROP TRIGGER IF EXISTS registry_historicalwebmapservice_delta_size ON registry_historicalwebmapservice;""",
    r"""DROP FUNCTION IF EXISTS registry_delta_size_historicalapplicationmetadatarecord();""",
    r"""DROP FUNCTION IF EXISTS registry_delta_size_historicalcatalogueservice();""",
    r"""DROP FUNCTION IF EXISTS registry_delta_size_historicaldatasetmetadatarecord();""",
    r"""DROP FUNCTION IF EXISTS registry_delta_size_historicalfeaturetype();""",
    r"""DROP FUNCTION IF EXISTS registry_delta_size_historicallayer();""",
    r"""DROP FUNCTION IF EXISTS registry_delta_size_historicalservicemetadatarecord();""",
    r"""DROP FUNCTION IF EXISTS registry_delta_size_historicalwebfeatureservice();""",
    r"""DROP FUNCTION IF EXISTS registry_delta_size_historicalwebmapservice();""",
]


class Migration(migrations.Migration):

    dependencies = [
        ("registry", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(CREATE_SQL, DROP_SQL),
    ]
