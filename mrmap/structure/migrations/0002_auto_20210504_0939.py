# Generated by Django 3.1.8 on 2021-05-04 07:39

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('structure', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='publishrequest',
            name='created_by_user',
            field=models.ForeignKey(blank=True, help_text='The user who has created this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='structure_publishrequest_created_by_user', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='publishrequest',
            name='from_organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='from_pending_publish_requests', to='structure.organization', verbose_name='requesting organization'),
        ),
        migrations.AddField(
            model_name='publishrequest',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, help_text='The last user who has modified this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='structure_publishrequest_last_modified_by', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='publishrequest',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, help_text='The organization which is the owner of this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='structure_publishrequest_owned_by_org', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddField(
            model_name='publishrequest',
            name='to_organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='to_pending_publish_requests', to='structure.organization', verbose_name='requested organization'),
        ),
        migrations.AddField(
            model_name='pendingtask',
            name='created_by_user',
            field=models.ForeignKey(blank=True, help_text='The user who has created this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='structure_pendingtask_created_by_user', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='pendingtask',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, help_text='The last user who has modified this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='structure_pendingtask_last_modified_by', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='pendingtask',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, help_text='The organization which is the owner of this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='structure_pendingtask_owned_by_org', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddField(
            model_name='organizationpublishrelation',
            name='from_organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='from_organizations', to='structure.organization'),
        ),
        migrations.AddField(
            model_name='organizationpublishrelation',
            name='to_organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='to_organizations', to='structure.organization'),
        ),
        migrations.AddField(
            model_name='organization',
            name='can_publish_for',
            field=models.ManyToManyField(blank=True, related_name='_organization_can_publish_for_+', related_query_name='publishers', through='structure.OrganizationPublishRelation', to='structure.Organization'),
        ),
        migrations.AddField(
            model_name='organization',
            name='created_by_user',
            field=models.ForeignKey(blank=True, help_text='The user who has created this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='structure_organization_created_by_user', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='organization',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, help_text='The last user who has modified this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='structure_organization_last_modified_by', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='organization',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, help_text='The organization which is the owner of this object.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='structure_organization_owned_by_org', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AlterUniqueTogether(
            name='publishrequest',
            unique_together={('from_organization', 'to_organization')},
        ),
        migrations.AlterUniqueTogether(
            name='organization',
            unique_together={('person_name', 'email', 'phone', 'facsimile', 'city', 'postal_code', 'address_type', 'address', 'state_or_province', 'country', 'description')},
        ),
    ]
