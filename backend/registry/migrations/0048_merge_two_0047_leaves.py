"""Merge of the two registry 0047 leaves that reached develop side by side.

Two branches each numbered their migration ``0047`` onto
``0046_explicit_keyword_through_models``:
``0047_harvestedmetadatarelation_harvested_day_state_job`` (from 8194f01c4,
the harvesting statistics index) and
``0047_temporarymdmetadatafile_attempt_count_and_more`` (from c342f9686, the
reference work permits of #1263). Each was green alone; develop's own QA is
red since the second merge ("Conflicting migrations detected; multiple leaf
nodes"). Neither side can renumber without rewriting a merged migration -
which is a person's act - so this is the schema-free merge node the graph
lacks: no operations, it only joins the two leaves into one.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('registry',
         '0047_harvestedmetadatarelation_harvested_day_state_job'),
        ('registry', '0047_temporarymdmetadatafile_attempt_count_and_more'),
    ]

    operations = []
