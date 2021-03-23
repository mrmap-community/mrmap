# Generated by Django 3.1.7 on 2021-03-23 18:55

import MrMap.validators
import datetime
import django.core.validators
from django.db import migrations, models
from django.utils.timezone import utc
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ErrorReport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('message', models.TextField()),
                ('traceback', models.TextField()),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('person_name', models.CharField(blank=True, default='', max_length=200, null=True, verbose_name='Contact person')),
                ('email', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='E-Mail')),
                ('phone', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Phone')),
                ('facsimile', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Facsimile')),
                ('city', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='City')),
                ('postal_code', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Postal code')),
                ('address_type', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Address type')),
                ('address', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Address')),
                ('state_or_province', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='State or province')),
                ('country', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Country')),
                ('organization_name', models.CharField(default='', help_text='The name of the organization', max_length=255, null=True, verbose_name='Organization name')),
                ('description', models.TextField(blank=True, default='', help_text='Describe what this organization representing', null=True, verbose_name='description')),
                ('is_auto_generated', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Organization',
                'verbose_name_plural': 'Organizations',
                'ordering': ['organization_name'],
            },
        ),
        migrations.CreateModel(
            name='PendingTask',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Last modified at')),
                ('task_id', models.CharField(blank=True, max_length=500, null=True)),
                ('description', models.TextField()),
                ('progress', models.FloatField(blank=True, default=0.0, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)])),
                ('remaining_time', models.DurationField(blank=True, null=True)),
                ('is_finished', models.BooleanField(default=False)),
                ('type', models.CharField(blank=True, choices=[(None, '---'), ('harvest', 'harvest'), ('register', 'register'), ('validate', 'validate')], max_length=500, null=True, validators=[MrMap.validators.validate_pending_task_enum_choices])),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PublishRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Last modified at')),
                ('message', models.TextField(blank=True, null=True)),
                ('activation_until', models.DateTimeField(default=datetime.datetime(2021, 4, 22, 18, 55, 20, 36666, tzinfo=utc))),
                ('is_accepted', models.BooleanField(default=False, verbose_name='accepted')),
            ],
            options={
                'verbose_name': 'Pending publish request',
                'verbose_name_plural': 'Pending publish requests',
            },
        ),
    ]
