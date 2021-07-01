# Generated by Django 3.2.4 on 2021-07-01 08:05

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('person_name', models.CharField(blank=True, default='', max_length=200, null=True, verbose_name='Contact person')),
                ('email', models.EmailField(blank=True, default='', max_length=100, null=True, verbose_name='E-Mail')),
                ('phone', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Phone')),
                ('facsimile', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Facsimile')),
                ('city', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='City')),
                ('postal_code', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Postal code')),
                ('address_type', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Address type')),
                ('address', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Address')),
                ('state_or_province', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='State or province')),
                ('country', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Country')),
                ('name', models.CharField(default='', help_text='The name of the organization', max_length=256, verbose_name='Name')),
                ('description', models.TextField(blank=True, default='', help_text='Describe what this organization representing', null=True, verbose_name='description')),
                ('is_autogenerated', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'Organization',
                'verbose_name_plural': 'Organizations',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='OrganizationPublishRelation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
        ),
        migrations.CreateModel(
            name='PublishRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('message', models.TextField(blank=True, null=True)),
                ('activation_until', models.DateTimeField(blank=True, null=True)),
                ('is_accepted', models.BooleanField(default=False, verbose_name='accepted')),
            ],
            options={
                'verbose_name': 'Pending publish request',
                'verbose_name_plural': 'Pending publish requests',
            },
        ),
    ]
