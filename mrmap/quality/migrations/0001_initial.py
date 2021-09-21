# Generated by Django 3.2.7 on 2021-09-21 12:30

from django.db import migrations, models
import django.db.models.deletion
import extras.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ConformityCheckConfiguration',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=1000)),
                ('metadata_types', models.JSONField()),
                ('conformity_type', models.TextField(choices=[('internal', 'internal'), ('etf', 'etf')])),
            ],
        ),
        migrations.CreateModel(
            name='Rule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=1000)),
                ('field_name', models.TextField(choices=[('title', 'title'), ('abstract', 'abstract'), ('access_constraints', 'access_constraints'), ('keywords', 'keywords'), ('formats', 'formats'), ('reference_system', 'reference_system')])),
                ('property', models.TextField(choices=[('len', 'len'), ('count', 'count')])),
                ('operator', models.TextField(choices=[('>', '>'), ('>=', '>='), ('<', '<'), ('<=', '<='), ('==', '=='), ('!=', '!=')])),
                ('threshold', models.TextField(null=True)),
            ],
        ),
        migrations.CreateModel(
            name='ConformityCheckConfigurationExternal',
            fields=[
                ('conformitycheckconfiguration_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='quality.conformitycheckconfiguration')),
                ('external_url', models.URLField(max_length=1000, null=True)),
                ('parameter_map', models.JSONField()),
                ('polling_interval_seconds', models.IntegerField(blank=True, default=5)),
                ('polling_interval_seconds_max', models.IntegerField(blank=True, default=300)),
            ],
            bases=('quality.conformitycheckconfiguration',),
        ),
        migrations.CreateModel(
            name='ConformityCheckConfigurationInternal',
            fields=[
                ('conformitycheckconfiguration_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='quality.conformitycheckconfiguration')),
            ],
            bases=('quality.conformitycheckconfiguration',),
        ),
        migrations.CreateModel(
            name='RuleSet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=1000)),
                ('rules', models.ManyToManyField(related_name='rule_set', to='quality.Rule')),
            ],
        ),
        migrations.CreateModel(
            name='ConformityCheckRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('passed', models.BooleanField(blank=True, null=True)),
                ('report', models.TextField(blank=True, null=True)),
                ('report_type', models.TextField(choices=[('text/html', 'text/html'), ('application/json', 'application/json')])),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='quality.conformitycheckconfiguration')),
            ],
            options={
                'ordering': ['-created_at'],
                'get_latest_by': '-created_at',
            },
            bases=(models.Model, extras.models.GenericModelMixin),
        ),
    ]
