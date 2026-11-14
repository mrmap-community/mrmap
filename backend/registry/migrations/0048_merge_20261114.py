"""Merges the two leaf migrations the registry app carries on develop.

Both 0047 migrations (``0047_harvestedmetadatarelation_harvested_day_state_job``
and ``0047_temporarymdmetadatafile_attempt_count_and_more``) arrived on develop
from different branches; ``makemigrations`` and ``migrate`` refuse the graph
with "Conflicting migrations detected; multiple leaf nodes" until one leaf
merges them, which no branch can build a test database without. The merge
carries no operations - it changes no schema.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("registry", "0047_harvestedmetadatarelation_harvested_day_state_job"),
        ("registry", "0047_temporarymdmetadatafile_attempt_count_and_more"),
    ]

    operations = []
