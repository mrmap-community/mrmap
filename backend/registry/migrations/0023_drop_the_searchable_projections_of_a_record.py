"""The two searchable projections of a metadata record are dropped (#855).

A projection of a record existed to be searched: it answered the keywords of a record as
an array and its text as a tsvector, both of which a record answers as a column of its
own since #853 and #854. What a search endpoint needed from it -- the kind of record it
answers -- is a constant of the queryset which answers one kind, see
``csw/queryables.py``. The CSW and the MapBender search answer the record tables
themselves now, so nothing reads these two projections anymore and nothing refreshes
them: the periodic task which rebuilt both every five minutes and the bulk write hooks
of the record managers which rebuilt them after every harvest document are gone with
them.

Both are dropped here instead of being left behind, and the way back answers their
statement itself. A projection is not part of the migration state -- django-pgviews
creates it from the model, see ``system.apps.sync_pg_views_if_missing`` -- and the models
which answered it are gone from the code, so the hook which watches for missing
projections cannot help on the way back: it does not know these two anymore. The
statement below is the one the models of the previous revision answered (a projection of
the columns of the record, extended by the constant which names the kind of record it
projects), which is what a deployment rolling back this migration finds again. The
indexes of a projection are not recreated with it; ``manage.py sync_pgviews --force``
creates those from the models a rolled back deployment checks out.
"""

import django_pgviews.db.migrations.operations
from django.db import migrations

DROP_SEARCHABLE_VIEWS = [
    "DROP MATERIALIZED VIEW IF EXISTS registry_searchabledatasetmetadatarecord;",
    "DROP MATERIALIZED VIEW IF EXISTS registry_searchableservicemetadatarecord;",
]

# the projections of a record as the models of the previous revision answered them: the
# columns of the record, because a record answers its keywords array and its vector
# itself since #853 and #854, plus the constant which tells the two kinds apart
CREATE_SEARCHABLE_DATASET_VIEW = """
CREATE MATERIALIZED VIEW registry_searchabledatasetmetadatarecord AS
    SELECT "registry_datasetmetadatarecord"."xml_backup_file",
           "registry_datasetmetadatarecord"."access_constraints",
           "registry_datasetmetadatarecord"."fees",
           "registry_datasetmetadatarecord"."use_limitation",
           "registry_datasetmetadatarecord"."license_source_note",
           "registry_datasetmetadatarecord"."licence_id",
           "registry_datasetmetadatarecord"."id",
           "registry_datasetmetadatarecord"."date_stamp",
           "registry_datasetmetadatarecord"."file_identifier",
           "registry_datasetmetadatarecord"."origin",
           "registry_datasetmetadatarecord"."origin_url",
           "registry_datasetmetadatarecord"."title",
           "registry_datasetmetadatarecord"."abstract",
           "registry_datasetmetadatarecord"."is_broken",
           "registry_datasetmetadatarecord"."is_customized",
           "registry_datasetmetadatarecord"."insufficient_quality",
           "registry_datasetmetadatarecord"."is_searchable",
           "registry_datasetmetadatarecord"."hits",
           "registry_datasetmetadatarecord"."inspire_interoperability",
           "registry_datasetmetadatarecord"."bounding_geometry",
           "registry_datasetmetadatarecord"."metadata_contact_id",
           "registry_datasetmetadatarecord"."equivalent_scale",
           "registry_datasetmetadatarecord"."ground_res",
           "registry_datasetmetadatarecord"."code",
           "registry_datasetmetadatarecord"."code_space",
           "registry_datasetmetadatarecord"."charset",
           "registry_datasetmetadatarecord"."resource_identifier",
           "registry_datasetmetadatarecord"."keywords_list",
           "registry_datasetmetadatarecord"."search_vector",
           "registry_datasetmetadatarecord"."dataset_contact_id",
           "registry_datasetmetadatarecord"."format",
           "registry_datasetmetadatarecord"."update_frequency_code",
           "registry_datasetmetadatarecord"."inspire_top_consistence",
           "registry_datasetmetadatarecord"."preview_image",
           "registry_datasetmetadatarecord"."lineage_statement",
           'dataset' AS "hierarchy_level"
      FROM "registry_datasetmetadatarecord"
WITH DATA;
"""

CREATE_SEARCHABLE_SERVICE_VIEW = """
CREATE MATERIALIZED VIEW registry_searchableservicemetadatarecord AS
    SELECT "registry_servicemetadatarecord"."xml_backup_file",
           "registry_servicemetadatarecord"."access_constraints",
           "registry_servicemetadatarecord"."fees",
           "registry_servicemetadatarecord"."use_limitation",
           "registry_servicemetadatarecord"."license_source_note",
           "registry_servicemetadatarecord"."licence_id",
           "registry_servicemetadatarecord"."id",
           "registry_servicemetadatarecord"."date_stamp",
           "registry_servicemetadatarecord"."file_identifier",
           "registry_servicemetadatarecord"."origin",
           "registry_servicemetadatarecord"."origin_url",
           "registry_servicemetadatarecord"."title",
           "registry_servicemetadatarecord"."abstract",
           "registry_servicemetadatarecord"."is_broken",
           "registry_servicemetadatarecord"."is_customized",
           "registry_servicemetadatarecord"."insufficient_quality",
           "registry_servicemetadatarecord"."is_searchable",
           "registry_servicemetadatarecord"."hits",
           "registry_servicemetadatarecord"."inspire_interoperability",
           "registry_servicemetadatarecord"."bounding_geometry",
           "registry_servicemetadatarecord"."metadata_contact_id",
           "registry_servicemetadatarecord"."equivalent_scale",
           "registry_servicemetadatarecord"."ground_res",
           "registry_servicemetadatarecord"."code",
           "registry_servicemetadatarecord"."code_space",
           "registry_servicemetadatarecord"."charset",
           "registry_servicemetadatarecord"."resource_identifier",
           "registry_servicemetadatarecord"."keywords_list",
           "registry_servicemetadatarecord"."search_vector",
           'service' AS "hierarchy_level"
      FROM "registry_servicemetadatarecord"
WITH DATA;
"""


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0022_datasetmetadatarecord_search_vector_and_more'),
    ]

    operations = [
        # a projection is a model which is not managed: its table is not Django's, so
        # Django's DeleteModel would drop it with DROP TABLE -- which postgres refuses
        # for a materialized view. The state of both models and of the bookkeeping
        # django-pgviews keeps for its views goes here, the statement which removes the
        # relation itself comes from below.
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(
                    name='SearchableDatasetMetadataRecord',
                ),
                migrations.DeleteModel(
                    name='SearchableServiceMetadataRecord',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='SearchableDatasetMetadataRecord',
                    materialized=True,
                    db_name='registry_searchabledatasetmetadatarecord',
                ),
                django_pgviews.db.migrations.operations.DeleteViewOperation(
                    name='SearchableServiceMetadataRecord',
                    materialized=True,
                    db_name='registry_searchableservicemetadatarecord',
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    DROP_SEARCHABLE_VIEWS,
                    [CREATE_SEARCHABLE_DATASET_VIEW, CREATE_SEARCHABLE_SERVICE_VIEW],
                ),
            ],
        ),
    ]
