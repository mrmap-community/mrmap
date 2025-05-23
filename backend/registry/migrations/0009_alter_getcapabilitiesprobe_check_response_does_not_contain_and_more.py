# Generated by Django 5.1.6 on 2025-02-28 09:28

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notify', '0008_alter_backgroundprocesslog_background_process'),
        ('registry', '0008_alter_harvestingjob_background_process_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='getcapabilitiesprobe',
            name='check_response_does_not_contain',
            field=models.CharField(blank=True, default='ExceptionReport>,ServiceException>', help_text='comma seperated search strings like: ExceptionReport>,ServiceException>', max_length=256, verbose_name='Check response does not contain'),
        ),
        migrations.AlterField(
            model_name='getmapprobe',
            name='check_response_does_not_contain',
            field=models.CharField(blank=True, default='ExceptionReport>,ServiceException>', help_text='comma seperated search strings like: ExceptionReport>,ServiceException>', max_length=256, verbose_name='Check response does not contain'),
        ),
        migrations.AlterField(
            model_name='harvestingjob',
            name='background_process',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.PROTECT, to='notify.backgroundprocess'),
        ),
        migrations.AlterField(
            model_name='historicalharvestingjob',
            name='background_process',
            field=models.ForeignKey(blank=True, db_constraint=False, editable=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='notify.backgroundprocess'),
        ),
    ]
