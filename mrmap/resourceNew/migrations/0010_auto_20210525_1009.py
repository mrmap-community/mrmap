# Generated by Django 3.1.8 on 2021-05-25 08:09

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('resourceNew', '0009_auto_20210525_0841'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='style',
            name='height',
        ),
        migrations.RemoveField(
            model_name='style',
            name='legend_uri',
        ),
        migrations.RemoveField(
            model_name='style',
            name='mime_type',
        ),
        migrations.RemoveField(
            model_name='style',
            name='width',
        ),
        migrations.AddField(
            model_name='dimension',
            name='extent',
            field=models.TextField(default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='dimension',
            name='name',
            field=models.CharField(default='', max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='dimension',
            name='units',
            field=models.CharField(default='', max_length=255),
            preserve_default=False,
        ),
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
        migrations.AlterField(
            model_name='style',
            name='layer',
            field=models.ForeignKey(editable=False, help_text='the layer for that this style is for.', on_delete=django.db.models.deletion.CASCADE, related_name='styles', related_query_name='style', to='resourceNew.layer', verbose_name='related layer'),
        ),
        migrations.AlterField(
            model_name='style',
            name='name',
            field=models.CharField(default='', editable=False, help_text="The style's Name is used in the Map request STYLES parameter to lookup the style on server side.", max_length=255, verbose_name='name'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='style',
            name='title',
            field=models.CharField(default='', editable=False, help_text='The Title is a human-readable string as an alternative for the name attribute.', max_length=255, verbose_name='title'),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='LegendUrl',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('legend_url', models.URLField(editable=False, help_text='contains the location of an image of a map legend appropriate to the enclosing Style.', max_length=4096)),
                ('height', models.IntegerField(editable=False, help_text='the size of the image in pixels')),
                ('width', models.IntegerField(editable=False, help_text='the size of the image in pixels')),
                ('mime_type', models.ForeignKey(editable=False, help_text='the mime type of the remote legend url', on_delete=django.db.models.deletion.PROTECT, related_name='legend_urls', related_query_name='legend_url', to='resourceNew.mimetype', verbose_name='internet mime type')),
                ('style', models.OneToOneField(editable=False, help_text='the style entity which is linked to this legend url', on_delete=django.db.models.deletion.CASCADE, related_name='style', related_query_name='style', to='resourceNew.style', verbose_name='related style')),
            ],
        ),
    ]
