# Generated by Django 3.1.7 on 2021-04-21 12:57

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
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('timestamp_start', models.DateTimeField(blank=True, null=True)),
                ('timestamp_end', models.DateTimeField(blank=True, null=True)),
                ('number_results', models.IntegerField(blank=True, null=True)),
                ('created', models.DateTimeField(auto_now_add=True, null=True)),
            ],
        ),
    ]
