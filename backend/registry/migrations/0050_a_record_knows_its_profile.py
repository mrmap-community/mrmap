# a record knows the profile it is authored under (#1240). The three record
# tables and the history tables that mirror them gain the column; existing
# rows are answered the `iso19139-generic` profile, the row the migration 0049
# seeded and the mapping the mapper configs of registry/mappers/configs
# actually implement today.
#
# The column is nullable and carries no default, and that is deliberate: a
# column default names the seeded row on every INSERT, while a
# `TransactionTestCase` truncates every table between tests and the default
# then violates the foreign key of a row no longer present -- which is what
# made the harvest and reference tasks fail on the first version of this
# migration. Records created afterwards answer the profile through
# `MetadataProfile.generic()` in the two creation paths (the mapper
# persistence and the api POST), a lookup which tolerates the same absence.

import uuid

import django.db.models.deletion
from django.db import migrations, models

GENERIC_ISO19139_PROFILE_PK = uuid.UUID('0180721f-bf34-4281-b367-648a74dd8ff9')

HELP_TEXT = ('the authoring profile whose sections and rules describe this '
             'record (#1240); records created by an import or through the api '
             'answer the seeded iso19139-generic profile, see '
             'MetadataProfile.generic()')


def assign_generic_profile(apps, schema_editor):
    """The existing records are records of the generic mapping.

    One UPDATE per record table -- an update of the column, not a save of the
    record: writing the audit rows of every record through the ORM would make
    the migration look like an edit of every record in the per-day statistics,
    which it is not.
    """
    profile_model = apps.get_model('registry', 'MetadataProfile')
    if not profile_model.objects.filter(
            pk=GENERIC_ISO19139_PROFILE_PK).exists():
        return
    for model_name in ('datasetmetadatarecord', 'servicemetadatarecord',
                       'applicationmetadatarecord'):
        model = apps.get_model('registry', model_name)
        model.objects.filter(profile__isnull=True).update(
            profile_id=GENERIC_ISO19139_PROFILE_PK)


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0049_the_profile_of_metadata_is_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='applicationmetadatarecord',
            name='profile',
            field=models.ForeignKey(blank=True, help_text=HELP_TEXT, null=True, on_delete=django.db.models.deletion.RESTRICT, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.AddField(
            model_name='datasetmetadatarecord',
            name='profile',
            field=models.ForeignKey(blank=True, help_text=HELP_TEXT, null=True, on_delete=django.db.models.deletion.RESTRICT, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.AddField(
            model_name='historicalapplicationmetadatarecord',
            name='profile',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text=HELP_TEXT, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.AddField(
            model_name='historicaldatasetmetadatarecord',
            name='profile',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text=HELP_TEXT, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.AddField(
            model_name='historicalservicemetadatarecord',
            name='profile',
            field=models.ForeignKey(blank=True, db_constraint=False, help_text=HELP_TEXT, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.AddField(
            model_name='servicemetadatarecord',
            name='profile',
            field=models.ForeignKey(blank=True, help_text=HELP_TEXT, null=True, on_delete=django.db.models.deletion.RESTRICT, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.RunPython(
            assign_generic_profile,
            migrations.RunPython.noop,
        ),
    ]
