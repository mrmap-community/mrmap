# Generated by Django 3.1.8 on 2021-06-07 14:07

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('csw', '0001_initial'),
        ('structure', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('service', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='harvestresult',
            name='created_by_user',
            field=models.ForeignKey(blank=True, editable=False, help_text='The user who has created this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='csw_harvestresult_created_by_user', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='harvestresult',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, editable=False, help_text='The last user who has modified this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='csw_harvestresult_last_modified_by', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='harvestresult',
            name='metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='harvest_results', to='service.metadata'),
        ),
        migrations.AddField(
            model_name='harvestresult',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, help_text='The organization which is the owner of this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='csw_harvestresult_owned_by_org', to='structure.organization', verbose_name='Owner'),
        ),
    ]