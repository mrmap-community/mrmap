# Generated by Django 3.1.8 on 2021-06-09 12:27

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('resourceNew', '0010_auto_20210609_1414'),
    ]

    operations = [
        migrations.AlterField(
            model_name='datasetmetadata',
            name='dataset_contact',
            field=models.ForeignKey(help_text='', on_delete=django.db.models.deletion.RESTRICT, related_name='dataset_contact_metadata', related_query_name='dataset_contact_metadata', to='resourceNew.metadatacontact', verbose_name='contact'),
        ),
        migrations.AlterField(
            model_name='datasetmetadata',
            name='insufficient_quality',
            field=models.TextField(help_text=''),
        ),
        migrations.AlterField(
            model_name='datasetmetadata',
            name='metadata_contact',
            field=models.ForeignKey(help_text='', on_delete=django.db.models.deletion.RESTRICT, related_name='metadata_contact_metadata', related_query_name='metadata_contact_metadata', to='resourceNew.metadatacontact', verbose_name='contact'),
        ),
        migrations.AlterField(
            model_name='featuretypemetadata',
            name='insufficient_quality',
            field=models.TextField(help_text=''),
        ),
        migrations.AlterField(
            model_name='layermetadata',
            name='insufficient_quality',
            field=models.TextField(help_text=''),
        ),
        migrations.AlterField(
            model_name='servicemetadata',
            name='insufficient_quality',
            field=models.TextField(help_text=''),
        ),
        migrations.AlterField(
            model_name='servicemetadata',
            name='metadata_contact',
            field=models.ForeignKey(help_text='', on_delete=django.db.models.deletion.RESTRICT, related_name='metadata_contact_service_metadata', related_query_name='metadata_contact_service_metadata', to='resourceNew.metadatacontact', verbose_name='contact'),
        ),
        migrations.AlterField(
            model_name='servicemetadata',
            name='service_contact',
            field=models.ForeignKey(help_text='', on_delete=django.db.models.deletion.RESTRICT, related_name='service_contact_service_metadata', related_query_name='service_contact_service_metadata', to='resourceNew.metadatacontact', verbose_name='contact'),
        ),
    ]