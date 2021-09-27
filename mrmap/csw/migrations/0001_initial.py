# Generated by Django 3.2.7 on 2021-09-27 13:25

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='HarvestResult',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('timestamp_start', models.DateTimeField(blank=True, null=True)),
                ('timestamp_end', models.DateTimeField(blank=True, null=True)),
                ('number_results', models.IntegerField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
