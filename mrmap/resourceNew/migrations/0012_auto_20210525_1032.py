# Generated by Django 3.1.8 on 2021-05-25 08:32

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('resourceNew', '0011_auto_20210525_1030'),
    ]

    operations = [
        migrations.AlterField(
            model_name='datasetmetadata',
            name='dataset_contact',
            field=models.ForeignKey(help_text='', on_delete=django.db.models.deletion.RESTRICT, related_name='dataset_contact_metadata', related_query_name='dataset_contact_metadata', to='resourceNew.metadatacontact', verbose_name='contact'),
        ),
        migrations.AlterField(
            model_name='datasetmetadata',
            name='is_searchable',
            field=models.BooleanField(default=False, help_text=''),
        ),
        migrations.AlterField(
            model_name='datasetmetadata',
            name='metadata_contact',
            field=models.ForeignKey(help_text='', on_delete=django.db.models.deletion.RESTRICT, related_name='metadata_contact_metadata', related_query_name='metadata_contact_metadata', to='resourceNew.metadatacontact', verbose_name='contact'),
        ),
        migrations.AlterField(
            model_name='layermetadata',
            name='is_searchable',
            field=models.BooleanField(default=False, help_text=''),
        ),
        migrations.AlterField(
            model_name='legendurl',
            name='mime_type',
            field=models.ForeignKey(editable=False, help_text='the mime type of the remote legend url', on_delete=django.db.models.deletion.PROTECT, related_name='legend_urls', related_query_name='legend_url', to='resourceNew.mimetype', verbose_name='internet mime type'),
        ),
        migrations.AlterField(
            model_name='legendurl',
            name='style',
            field=models.OneToOneField(editable=False, help_text='the style entity which is linked to this legend url', on_delete=django.db.models.deletion.CASCADE, related_name='legend_url', related_query_name='legend_url', to='resourceNew.style', verbose_name='related style'),
        ),
        migrations.AlterField(
            model_name='servicemetadata',
            name='is_searchable',
            field=models.BooleanField(default=False, help_text=''),
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
