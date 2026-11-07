"""Gives a harvesting run the moment it was made, and fills the runs which have one.

``ProcessingData.date_created`` carried the comment which explains why ``auto_now_add`` is the
wrong tool for a creation stamp - it ignores a value handed to it - and then never answered the
default the comment asks for instead. So the column of every run the harvesting made stayed
NULL (#1079), which is read in the screens as three different bugs:

* ``sort=-date_created``, a sort the endpoint offers (``views/harvesting.py``), answers the runs
  in whatever order the database happens to give - the card of a catalogue which asks for the
  three most recent runs of its catalogue shows three runs which are not those three;
* every elapsed time on a run is empty, so #1071 had to read the first row of the change log to
  answer how long a harvest took, and #692 had to add ``done_at`` to the sortable fields because
  ``-date_created`` - the default ordering of the model - ordered nothing;
* the time range filters of #1080 can only be answered once the column holds a value.

The field gets the ``default=now`` its sibling in ``notify/models.py`` already has. ``null=True``
stays: a run whose creation cannot be known has to stay markable as unknown, which is what the
screens answer "not recorded" instead of inventing a moment. An explicit moment still wins over
the default - which is what the scenarios of #870 and the migration below depend on.

The rows a deployment already has are filled from its own change log: the earliest revision of a
job is the moment that job was made, which is exactly the row ``harvest_durations()`` of
``querys/harvest_history.py`` reads when the column is empty. Reading the same row keeps the
filled value and the fallback of #1071 the same moment, so no duration of a catalogue changes
with this migration. A job whose change log is gone - revisions are pruned, and a row can predate
the audit trail - keeps its empty value and is not given an invented date.

The other runs the field's comment mentions answer their own creation already: the update jobs
declare ``auto_now_add`` and the monitoring runs a ``default=now`` on their own fields, so both
are ordered by ``-date_created`` on real values today and need nothing here.
"""
import django.utils.timezone
from django.db import migrations, models

#: the creation of every run whose own column is still empty, read from the earliest revision of
#: its change log. One statement, because a deployment which harvested for years has thousands of
#: runs and one ``UPDATE`` per row would be thousands of statements. ``history_id`` breaks a tie
#: between revisions written in the same moment, as ``harvest_durations()`` orders it.
CREATION_FROM_CHANGE_LOG = """
    UPDATE registry_harvestingjob job
       SET date_created = made.history_date
      FROM (SELECT DISTINCT ON (history_relation_id)
                   history_relation_id,
                   history_date
              FROM registry_historicalharvestingjob
             ORDER BY history_relation_id, history_date, history_id) made
     WHERE job.date_created IS NULL
       AND made.history_relation_id = job.id
"""


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0034_remove_harvestedmetadatarelation_dm_record_or_sm_record_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='harvestingjob',
            name='date_created',
            field=models.DateTimeField(blank=True, default=django.utils.timezone.now, help_text='Datetime field when the process was created in UTC', null=True, verbose_name='Created DateTime'),
        ),
        migrations.AlterField(
            model_name='historicalharvestingjob',
            name='date_created',
            field=models.DateTimeField(blank=True, default=django.utils.timezone.now, help_text='Datetime field when the process was created in UTC', null=True, verbose_name='Created DateTime'),
        ),
        # The reverse of the fill is nothing: the moments it wrote are read out of the change log
        # and stay true afterwards, and a run which stayed empty stays empty. Setting the filled
        # rows back to NULL would destroy what the upgrade just recovered, the same way the
        # backfill of 0025 is not undone.
        migrations.RunSQL(CREATION_FROM_CHANGE_LOG, migrations.RunSQL.noop),
    ]
