# Generated by Django 5.1.2 on 2025-02-13 16:20

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notify', '0007_backgroundprocesslog'),
    ]

    operations = [
        migrations.AlterField(
            model_name='backgroundprocesslog',
            name='background_process',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', related_query_name='log', to='notify.backgroundprocess'),
        ),
    ]
