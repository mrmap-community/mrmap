"""The searchable representation of a metadata record as a column of the record.

The vector which a search hits is derived from the record itself, so postgres derives
it: a stored generated column is computed for every written row, which makes a record
findable the moment it is stored. Nothing has to be rebuilt for that and no window
exists in which a stored record is not findable; the expression and the two rules of
postgres it is written around - no parameters, no function which is not immutable -
live in ``registry/expressions/search.py``.

Both record tables get the column and a GIN index for it: a tsquery is a containment
over a tsvector which no btree comparison answers. Adding a stored generated column
computes the expression for every row of the table, so on a deployment with many
metadata records this migration rewrites both record tables while holding their
exclusive lock, and the same is true of the two GIN indexes.

The way back drops the two searchable projections of a record first, see below.
"""

import django.contrib.postgres.indexes
import django.contrib.postgres.search
import registry.expressions.search
from django.db import migrations, models

# the searchable projections of a record answer the vector of it, which means they
# depend on the column: to drop the column they have to go first. A projection is not
# part of the migration state - django-pgviews creates it from the model, which is why
# it cannot be dropped by RemoveField - so the way back drops it here and the hook
# which watches for missing projections (system.apps.sync_pg_views_if_missing) creates
# it again, with the definition the checked out code answers. Without this the down
# revision fails on postgres with "cannot drop column search_vector of table
# registry_servicemetadatarecord because other objects depend on it".
DROP_SEARCHABLE_VIEWS = [
    "DROP MATERIALIZED VIEW IF EXISTS registry_searchabledatasetmetadatarecord;",
    "DROP MATERIALIZED VIEW IF EXISTS registry_searchableservicemetadatarecord;",
]


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0021_metadatarecords_keywords_list'),
    ]

    operations = [
        migrations.AddField(
            model_name='datasetmetadatarecord',
            name='search_vector',
            field=models.GeneratedField(db_persist=True, expression=registry.expressions.search.MetadataRecordSearchVector(), output_field=django.contrib.postgres.search.SearchVectorField()),
        ),
        migrations.AddField(
            model_name='servicemetadatarecord',
            name='search_vector',
            field=models.GeneratedField(db_persist=True, expression=registry.expressions.search.MetadataRecordSearchVector(), output_field=django.contrib.postgres.search.SearchVectorField()),
        ),
        migrations.AddIndex(
            model_name='datasetmetadatarecord',
            index=django.contrib.postgres.indexes.GinIndex(fields=['search_vector'], name='registry_da_search__7a3c56_gin'),
        ),
        migrations.AddIndex(
            model_name='servicemetadatarecord',
            index=django.contrib.postgres.indexes.GinIndex(fields=['search_vector'], name='registry_se_search__2b20f5_gin'),
        ),
        # last, so that it is the first thing the way back does; nothing to do coming
        # forward: the projections of a record answer the column of it instead of
        # computing a vector of their own, which is a change of what the models answer
        # and not of the statement of a table
        migrations.RunSQL(migrations.RunSQL.noop, DROP_SEARCHABLE_VIEWS),
    ]
