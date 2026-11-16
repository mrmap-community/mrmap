# Data migration prepared by hand, referenced by the following AlterFields:
# the correlation columns of CeleryTaskAttempt stop accepting NULL, so the
# rows written before carry their "this task has no root, no parent and no
# periodic name" as the empty string - the very value the collector writes
# today.

from django.db import migrations

ATTEMPT_FIELDS = ['root_id', 'parent_id', 'periodic_name']


def nulls_to_empty(apps, schema_editor):
    model = apps.get_model('system', 'CeleryTaskAttempt')
    for field in ATTEMPT_FIELDS:
        model.objects.filter(**{f'{field}__isnull': True}).update(
            **{field: ''})


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0002_celery_attempt_samples'),
    ]

    operations = [
        migrations.RunPython(nulls_to_empty, migrations.RunPython.noop),
    ]
