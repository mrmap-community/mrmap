"""The ``skipped`` outcome of a fire the singleton lock refused (#1827).

Choices-only change: ``AttemptOutcome`` gained ``skipped``, the answer a fire
of a ``SingletonTask`` which found the lock taken leaves behind. The column
already stores any 16-character string, so no data moves and no constraint
changes - the two unique constraints of the table key on ``outcome`` being
empty or not, and ``skipped`` is not empty, so a dropped fire lands on the
terminal side of both like every other outcome.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('system', '0005_celerytaskattempt_attempt_recorded_idx'),
    ]

    operations = [
        migrations.AlterField(
            model_name='celerytaskattempt',
            name='outcome',
            field=models.CharField(
                blank=True,
                choices=[('success', 'Success'), ('failure', 'Failure'),
                         ('retry', 'Retry'), ('revoked', 'Revoked'),
                         ('skipped', 'Skipped')],
                default='', max_length=16),
        ),
    ]
