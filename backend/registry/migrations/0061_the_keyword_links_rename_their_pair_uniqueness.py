# The three explicit keyword through models of `registry/models/metadata.py`
# declare the pair uniqueness of their table as a `UniqueConstraint` now
# instead of the deprecated `unique_together` (#1483). What changes is the name
# the index carries, not the index: `makemigrations` answers this conversion
# with a drop and a rebuild, which on the keyword tables of a loaded deployment
# means an ACCESS EXCLUSIVE lock for as long as a unique index takes to build.
# So each operation states the new constraint in Django's state and renames the
# constraint which is already there - and with it its backing index - in place.
#
# The old names are the ones `unique_together` gave these constraints when the
# tables were still the automatic tables of the M2M relations
# (`registry/migrations/0046_explicit_keyword_through_models.py` moved their
# state, not their schema), and the tables are the ones each model names with
# its `db_table`.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0060_the_dataset_coupling_is_unique_per_kind'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterUniqueTogether(
                    name='datasetmetadatarecordkeywordslink',
                    unique_together=set()),
                migrations.AddConstraint(
                    model_name='datasetmetadatarecordkeywordslink',
                    constraint=models.UniqueConstraint(
                        fields=('datasetmetadatarecord', 'keyword'),
                        name='unique_keyword_per_dataset_metadata_record'),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "registry_datasetmetadatarecord_keywords"'
                        ' RENAME CONSTRAINT'
                        ' "registry_datasetmetadata_datasetmetadatarecord_id_048bec0c_uniq"'
                        ' TO "unique_keyword_per_dataset_metadata_record"'),
                    reverse_sql=(
                        'ALTER TABLE "registry_datasetmetadatarecord_keywords"'
                        ' RENAME CONSTRAINT'
                        ' "unique_keyword_per_dataset_metadata_record"'
                        ' TO "registry_datasetmetadata_datasetmetadatarecord_id_048bec0c_uniq"'),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterUniqueTogether(
                    name='servicemetadatarecordkeywordslink',
                    unique_together=set()),
                migrations.AddConstraint(
                    model_name='servicemetadatarecordkeywordslink',
                    constraint=models.UniqueConstraint(
                        fields=('servicemetadatarecord', 'keyword'),
                        name='unique_keyword_per_service_metadata_record'),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "registry_servicemetadatarecord_keywords"'
                        ' RENAME CONSTRAINT'
                        ' "registry_servicemetadata_servicemetadatarecord_id_fa0e5a89_uniq"'
                        ' TO "unique_keyword_per_service_metadata_record"'),
                    reverse_sql=(
                        'ALTER TABLE "registry_servicemetadatarecord_keywords"'
                        ' RENAME CONSTRAINT'
                        ' "unique_keyword_per_service_metadata_record"'
                        ' TO "registry_servicemetadata_servicemetadatarecord_id_fa0e5a89_uniq"'),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterUniqueTogether(
                    name='applicationmetadatarecordkeywordslink',
                    unique_together=set()),
                migrations.AddConstraint(
                    model_name='applicationmetadatarecordkeywordslink',
                    constraint=models.UniqueConstraint(
                        fields=('applicationmetadatarecord', 'keyword'),
                        name='unique_keyword_per_application_metadata_record'),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "registry_applicationmetadatarecord_keywords"'
                        ' RENAME CONSTRAINT'
                        ' "registry_applicationmeta_applicationmetadatarecor_92a49891_uniq"'
                        ' TO "unique_keyword_per_application_metadata_record"'),
                    reverse_sql=(
                        'ALTER TABLE "registry_applicationmetadatarecord_keywords"'
                        ' RENAME CONSTRAINT'
                        ' "unique_keyword_per_application_metadata_record"'
                        ' TO "registry_applicationmeta_applicationmetadatarecor_92a49891_uniq"'),
                ),
            ],
        ),
    ]
