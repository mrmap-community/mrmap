# Generated by Django 3.2.7 on 2021-09-27 13:25

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('acls', '0001_initial'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='accesscontrollist',
            name='accessible_organizations',
            field=models.ManyToManyField(blank=True, help_text='Select which organizations shall be accessible with the configured permissions.', to='users.Organization', verbose_name='Accessible organizations'),
        ),
        migrations.AddField(
            model_name='accesscontrollist',
            name='created_by_user',
            field=models.ForeignKey(blank=True, editable=False, help_text='The user who has created this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acls_accesscontrollist_created_by_user', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='accesscontrollist',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, editable=False, help_text='The last user who has modified this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acls_accesscontrollist_last_modified_by', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='accesscontrollist',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, editable=False, help_text='The organization which is the owner of this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='acls_accesscontrollist_owned_by_org', to='users.organization', verbose_name='Owner'),
        ),
    ]
