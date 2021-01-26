# Generated by Django 3.1.5 on 2021-01-25 12:58

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='HealthState',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('health_state_code', models.CharField(choices=[('ok', 'ok'), ('warning', 'warning'), ('critical', 'critical'), ('unknown', 'unknown'), ('unauthorized', 'unauthorized')], default='unknown', max_length=12)),
                ('health_message', models.CharField(default='The health state is unknown, cause no health checks runs for this resource.', max_length=512)),
                ('reliability_1w', models.FloatField(default=0, validators=[django.core.validators.MaxValueValidator(100), django.core.validators.MinValueValidator(1)])),
                ('reliability_1m', models.FloatField(default=0, validators=[django.core.validators.MaxValueValidator(100), django.core.validators.MinValueValidator(1)])),
                ('reliability_3m', models.FloatField(default=0, validators=[django.core.validators.MaxValueValidator(100), django.core.validators.MinValueValidator(1)])),
                ('average_response_time', models.DurationField(blank=True, null=True)),
                ('average_response_time_1w', models.DurationField(blank=True, null=True)),
                ('average_response_time_1m', models.DurationField(blank=True, null=True)),
                ('average_response_time_3m', models.DurationField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name='HealthStateReason',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.TextField(verbose_name='Reason')),
                ('health_state_code', models.CharField(choices=[('ok', 'ok'), ('warning', 'warning'), ('critical', 'critical'), ('unknown', 'unknown'), ('unauthorized', 'unauthorized')], default='unknown', max_length=12)),
            ],
        ),
        migrations.CreateModel(
            name='Monitoring',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('duration', models.DurationField(blank=True, null=True)),
                ('status_code', models.IntegerField(blank=True, null=True)),
                ('error_msg', models.TextField(blank=True, null=True)),
                ('available', models.BooleanField(null=True)),
                ('monitored_uri', models.CharField(max_length=2000)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='MonitoringRun',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('start', models.DateTimeField(auto_now_add=True)),
                ('end', models.DateTimeField(blank=True, null=True)),
                ('duration', models.DurationField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-end'],
            },
        ),
        migrations.CreateModel(
            name='MonitoringSetting',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('check_time', models.TimeField()),
                ('timeout', models.IntegerField()),
            ],
        ),
        migrations.CreateModel(
            name='MonitoringCapability',
            fields=[
                ('monitoring_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='monitoring.monitoring')),
                ('needs_update', models.BooleanField(blank=True, null=True)),
                ('diff', models.TextField(blank=True, null=True)),
            ],
            bases=('monitoring.monitoring',),
        ),
    ]
