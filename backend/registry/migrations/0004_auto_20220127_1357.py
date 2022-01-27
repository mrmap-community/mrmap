# Generated by Django 3.2.9 on 2022-01-27 12:57

from django.db import migrations, models
import django.db.models.deletion
import registry.models.harvest


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0003_auto_20220125_1444'),
    ]

    operations = [
        migrations.CreateModel(
            name='HarvestingJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_records', models.IntegerField(blank=True, editable=False, help_text='total count of records which will be harvested by this job', null=True, verbose_name='total records')),
                ('step_size', models.IntegerField(blank=True, default=50)),
                ('started_at', models.DateTimeField(blank=True, editable=False, help_text='timestamp of start', null=True, verbose_name='date started')),
                ('done_at', models.DateTimeField(blank=True, editable=False, help_text='timestamp of done', null=True, verbose_name='date done')),
                ('existing_records', models.ManyToManyField(editable=False, related_name='ignored_by', to='registry.DatasetMetadata')),
                ('new_records', models.ManyToManyField(editable=False, related_name='harvested_by', to='registry.DatasetMetadata')),
                ('service', models.ForeignKey(help_text='the csw for that this job is running', on_delete=django.db.models.deletion.CASCADE, to='registry.catalougeservice', verbose_name='service')),
                ('updated_records', models.ManyToManyField(editable=False, related_name='updated_by', to='registry.DatasetMetadata')),
            ],
            options={
                'ordering': ['-done_at'],
                'get_latest_by': 'done_at',
            },
        ),
        migrations.CreateModel(
            name='TemporaryMdMetadataFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('md_metadata_file', models.FileField(editable=False, help_text='the content of the http response', upload_to=registry.models.harvest.response_file_path, verbose_name='response')),
                ('job', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='registry.harvestingjob', verbose_name='harvesting job')),
            ],
        ),
        migrations.AddConstraint(
            model_name='harvestingjob',
            constraint=models.UniqueConstraint(fields=('service', 'done_at'), name='registry_harvestingjob_service_done_at_uniq'),
        ),
        migrations.AddConstraint(
            model_name='harvestingjob',
            constraint=models.UniqueConstraint(condition=models.Q(('done_at__isnull', True)), fields=('service',), name='registry_harvestingjob_service_uniq'),
        ),
    ]