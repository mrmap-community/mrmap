# Generated by Django 3.1.7 on 2021-04-26 11:53

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import mptt.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('service', '0001_initial'),
        ('structure', '0002_auto_20210426_1353'),
    ]

    operations = [
        migrations.AddField(
            model_name='service',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_service_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='service',
            name='is_update_candidate_for',
            field=models.OneToOneField(blank=True, default=None, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='has_update_candidate', to='service.service'),
        ),
        migrations.AddField(
            model_name='service',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_service_lastmodified', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='service',
            name='metadata',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='service', to='service.metadata'),
        ),
        migrations.AddField(
            model_name='service',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_service_owned', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddField(
            model_name='service',
            name='parent_service',
            field=models.ForeignKey(blank=True, default=None, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='child_services', to='service.service'),
        ),
        migrations.AddField(
            model_name='service',
            name='service_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.DO_NOTHING, to='service.servicetype'),
        ),
        migrations.AlterUniqueTogether(
            name='referencesystem',
            unique_together={('code', 'prefix')},
        ),
        migrations.AddField(
            model_name='proxylog',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_proxylog_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='proxylog',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_proxylog_lastmodified', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='proxylog',
            name='metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='service.metadata'),
        ),
        migrations.AddField(
            model_name='proxylog',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_proxylog_owned', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddField(
            model_name='proxylog',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterUniqueTogether(
            name='mimetype',
            unique_together={('operation', 'mime_type')},
        ),
        migrations.AddField(
            model_name='metadatarelation',
            name='from_metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='from_metadatas', to='service.metadata'),
        ),
        migrations.AddField(
            model_name='metadatarelation',
            name='to_metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='to_metadatas', to='service.metadata'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='additional_urls',
            field=models.ManyToManyField(blank=True, to='service.GenericUrl'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='categories',
            field=models.ManyToManyField(blank=True, to='service.Category'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='contact',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='structure.organization', verbose_name='Data provider'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_metadata_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='dimensions',
            field=models.ManyToManyField(blank=True, to='service.Dimension'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='formats',
            field=models.ManyToManyField(blank=True, to='service.MimeType'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='keywords',
            field=models.ManyToManyField(to='service.Keyword'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_metadata_lastmodified', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='legal_dates',
            field=models.ManyToManyField(blank=True, to='service.LegalDate'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='legal_reports',
            field=models.ManyToManyField(blank=True, to='service.LegalReport'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='licence',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='service.licence'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_metadata_owned', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='reference_system',
            field=models.ManyToManyField(blank=True, to='service.ReferenceSystem'),
        ),
        migrations.AddField(
            model_name='metadata',
            name='related_metadatas',
            field=models.ManyToManyField(blank=True, related_name='related_to', through='service.MetadataRelation', to='service.Metadata'),
        ),
        migrations.AddField(
            model_name='legalreport',
            name='date',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='service.legaldate'),
        ),
        migrations.AddIndex(
            model_name='keyword',
            index=models.Index(fields=['keyword'], name='service_key_keyword_a43a85_idx'),
        ),
        migrations.AddField(
            model_name='featuretypeelement',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_featuretypeelement_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='featuretypeelement',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_featuretypeelement_lastmodified', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='featuretypeelement',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_featuretypeelement_owned', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddField(
            model_name='featuretype',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_featuretype_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='featuretype',
            name='default_srs',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='default_srs', to='service.referencesystem'),
        ),
        migrations.AddField(
            model_name='featuretype',
            name='elements',
            field=models.ManyToManyField(to='service.FeatureTypeElement'),
        ),
        migrations.AddField(
            model_name='featuretype',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_featuretype_lastmodified', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='featuretype',
            name='metadata',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='featuretype', to='service.metadata'),
        ),
        migrations.AddField(
            model_name='featuretype',
            name='namespaces',
            field=models.ManyToManyField(to='service.Namespace'),
        ),
        migrations.AddField(
            model_name='featuretype',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_featuretype_owned', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddField(
            model_name='featuretype',
            name='parent_service',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='featuretypes', to='service.service'),
        ),
        migrations.AddField(
            model_name='externalauthentication',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_externalauthentication_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='externalauthentication',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_externalauthentication_lastmodified', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='externalauthentication',
            name='metadata',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='external_authentication', to='service.metadata'),
        ),
        migrations.AddField(
            model_name='externalauthentication',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_externalauthentication_owned', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddField(
            model_name='document',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_document_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='document',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_document_lastmodified', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='document',
            name='metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='service.metadata'),
        ),
        migrations.AddField(
            model_name='document',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_document_owned', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddField(
            model_name='dataset',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_dataset_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='dataset',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_dataset_lastmodified', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='dataset',
            name='metadata',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='dataset', to='service.metadata'),
        ),
        migrations.AddField(
            model_name='dataset',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_dataset_owned', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddIndex(
            model_name='category',
            index=models.Index(fields=['title_EN'], name='service_cat_title_E_d0a3ab_idx'),
        ),
        migrations.AddField(
            model_name='allowedoperation',
            name='allowed_groups',
            field=models.ManyToManyField(related_name='allowed_operations', to='auth.Group'),
        ),
        migrations.AddField(
            model_name='allowedoperation',
            name='created_by_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_allowedoperation_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by'),
        ),
        migrations.AddField(
            model_name='allowedoperation',
            name='last_modified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_allowedoperation_lastmodified', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by'),
        ),
        migrations.AddField(
            model_name='allowedoperation',
            name='operations',
            field=models.ManyToManyField(related_name='allowed_operations', to='service.OGCOperation'),
        ),
        migrations.AddField(
            model_name='allowedoperation',
            name='owned_by_org',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='service_allowedoperation_owned', to='structure.organization', verbose_name='Owner'),
        ),
        migrations.AddField(
            model_name='allowedoperation',
            name='root_metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='service.metadata'),
        ),
        migrations.AddField(
            model_name='allowedoperation',
            name='secured_metadata',
            field=models.ManyToManyField(related_name='allowed_operations', to='service.Metadata'),
        ),
        migrations.AddField(
            model_name='style',
            name='layer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='style', to='service.layer'),
        ),
        migrations.AddField(
            model_name='service',
            name='operation_urls',
            field=models.ManyToManyField(to='service.ServiceUrl'),
        ),
        migrations.AddIndex(
            model_name='metadata',
            index=models.Index(fields=['id', 'identifier'], name='service_met_id_0adfe4_idx'),
        ),
        migrations.AddField(
            model_name='layer',
            name='parent',
            field=mptt.fields.TreeForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='service.layer'),
        ),
    ]