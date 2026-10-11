from django.db import migrations, models


def populate_status(apps, schema_editor):
    BackgroundProcess = apps.get_model('notify', 'BackgroundProcess')
    processes = BackgroundProcess.objects.using(schema_editor.connection.alias)
    processes.filter(done_at__isnull=False).update(status=2)
    processes.filter(done_at__isnull=True, threads__status__in=[
        'PENDING', 'RECEIVED', 'STARTED', 'RETRY', 'REJECTED']).update(status=1)
    processes.filter(phase='abort').update(status=4)


class Migration(migrations.Migration):
    dependencies = [('notify', '0002_alter_backgroundprocess_date_created_and_more')]

    operations = [
        migrations.AddField(
            model_name='backgroundprocess',
            name='status',
            field=models.PositiveSmallIntegerField(
                choices=[(0, 'pending'), (1, 'running'),
                         (2, 'completed'), (3, 'failed'),
                         (4, 'aborted')],
                default=0, editable=False),
        ),
        migrations.RunPython(populate_status, migrations.RunPython.noop),
    ]
