# a record knows the profile it is authored under (#1240). The three record
# tables and the history tables that mirror them gain the column; existing
# rows are born as `iso19139-generic`, the row the migration 0049 seeded and
# the mapping the mapper configs of registry/mappers/configs actually
# implement today.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0049_the_profile_of_metadata_is_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='applicationmetadatarecord',
            name='profile',
            field=models.ForeignKey(default=uuid.UUID('0180721f-bf34-4281-b367-648a74dd8ff9'), help_text='the authoring profile whose sections and rules describe this record (#1240); every record mapped by the configs of registry/mappers/configs is an iso19139-generic one, which is why the default names that seeded row', on_delete=django.db.models.deletion.RESTRICT, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.AddField(
            model_name='datasetmetadatarecord',
            name='profile',
            field=models.ForeignKey(default=uuid.UUID('0180721f-bf34-4281-b367-648a74dd8ff9'), help_text='the authoring profile whose sections and rules describe this record (#1240); every record mapped by the configs of registry/mappers/configs is an iso19139-generic one, which is why the default names that seeded row', on_delete=django.db.models.deletion.RESTRICT, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.AddField(
            model_name='historicalapplicationmetadatarecord',
            name='profile',
            field=models.ForeignKey(blank=True, db_constraint=False, default=uuid.UUID('0180721f-bf34-4281-b367-648a74dd8ff9'), help_text='the authoring profile whose sections and rules describe this record (#1240); every record mapped by the configs of registry/mappers/configs is an iso19139-generic one, which is why the default names that seeded row', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.AddField(
            model_name='historicaldatasetmetadatarecord',
            name='profile',
            field=models.ForeignKey(blank=True, db_constraint=False, default=uuid.UUID('0180721f-bf34-4281-b367-648a74dd8ff9'), help_text='the authoring profile whose sections and rules describe this record (#1240); every record mapped by the configs of registry/mappers/configs is an iso19139-generic one, which is why the default names that seeded row', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.AddField(
            model_name='historicalservicemetadatarecord',
            name='profile',
            field=models.ForeignKey(blank=True, db_constraint=False, default=uuid.UUID('0180721f-bf34-4281-b367-648a74dd8ff9'), help_text='the authoring profile whose sections and rules describe this record (#1240); every record mapped by the configs of registry/mappers/configs is an iso19139-generic one, which is why the default names that seeded row', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
        migrations.AddField(
            model_name='servicemetadatarecord',
            name='profile',
            field=models.ForeignKey(default=uuid.UUID('0180721f-bf34-4281-b367-648a74dd8ff9'), help_text='the authoring profile whose sections and rules describe this record (#1240); every record mapped by the configs of registry/mappers/configs is an iso19139-generic one, which is why the default names that seeded row', on_delete=django.db.models.deletion.RESTRICT, related_name='+', to='registry.metadataprofile', verbose_name='metadata profile'),
        ),
    ]
