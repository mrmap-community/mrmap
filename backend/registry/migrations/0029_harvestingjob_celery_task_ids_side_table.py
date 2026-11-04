"""Moves the task ids of a harvesting job into a table of their own.

The array field grew with every chord the job published and every ordinary read
of the job row loaded and parsed it - a job which survived a few crash and
recovery cycles of a backlog of hundreds of thousands of files cost seconds per
request (#892). The ids are the shadow a job keeps in the database of the
messages it has in the broker: an id is registered when its task is published
and removed again when the task reports in or the job is aborted, so what the
table holds is the work an abort could still revoke.

#971: a harvest which was running while a deployment updated had already
registered ids in the array, and declaring only ``RemoveField`` and
``CreateModel`` dropped them with the column. The first worker restart after
such an upgrade then re-publishes the whole remaining backlog of that harvest
on top of the messages which are still queued, because the recovery reads an
empty shadow as "nothing of this run lives in the broker" (#891), and an abort
has nothing left to revoke. So the history carries the data: between the new
table and the dropped column, one statement splits the array of every job into
one row per id. The first entry of the array is the id of the delivery which
created the job - ``create_harvesting_job`` registers the delivery before the
job publishes any work, and a redelivery of that message has to find this job
instead of starting a second harvest, which is why the flag exists and why the
entry leads. The rest are ids of its work. A job whose array was empty has
nothing to carry, and an id which another job registered first cannot win the
unique key twice - the harvest which owns the row is the one whose revocation
reaches the task. The column of ``historicalharvestingjob`` is only dropped: a
stored revision of a job never drives a revocation or a recovery.

The copy is one statement and not a loop over the models, because in the
revision where both shapes exist at once the reverse name of the new foreign
key is ``celery_task_ids`` as well, and that descriptor claims the attribute of
the old column: while the copy has to read the array and write the rows, no
historical model instance can carry both.
"""
import django.db.models.deletion
from django.db import migrations, models

#: splits every job's array into one row per id, the first entry as the
#: creation id; a null or empty array answers no row, and an id which is
#: registered for another job first is dropped rather than breaking the upgrade
CARRY_FORWARD = """
    INSERT INTO registry_harvestingjobtaskid (job_id, task_id, creation)
    SELECT job.id, registered.task_id, registered.ordinality = 1
      FROM registry_harvestingjob job
 CROSS JOIN LATERAL unnest(job.celery_task_ids)
            WITH ORDINALITY AS registered(task_id, ordinality)
    ON CONFLICT (task_id) DO NOTHING
"""

#: puts the rows of every job back into its array, the creation id in front as
#: the copy read it and the work of a run behind it in the order it was written
CARRY_BACK = """
    UPDATE registry_harvestingjob job
       SET celery_task_ids = carried.ids
      FROM (SELECT job_id,
                   array_agg(task_id ORDER BY creation DESC, id) AS ids
              FROM registry_harvestingjobtaskid
             GROUP BY job_id) carried
     WHERE job.id = carried.job_id
"""


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0028_a_keyword_is_as_long_as_its_catalogue_says'),
    ]

    operations = [
        # the table has to exist while the array does, the copy reads one and
        # writes the other; reversing runs the operations in the other order:
        # the columns come back, the arrays are rebuilt and the table is dropped
        migrations.CreateModel(
            name='HarvestingJobTaskId',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_id', models.UUIDField(unique=True)),
                ('creation', models.BooleanField(default=False)),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='celery_task_ids', related_query_name='celery_task_id', to='registry.harvestingjob')),
            ],
        ),
        migrations.RunSQL(CARRY_FORWARD, CARRY_BACK),
        migrations.RemoveField(
            model_name='harvestingjob',
            name='celery_task_ids',
        ),
        migrations.RemoveField(
            model_name='historicalharvestingjob',
            name='celery_task_ids',
        ),
    ]
