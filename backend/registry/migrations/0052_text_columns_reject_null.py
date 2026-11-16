# Data migration prepared by hand, referenced by the following AlterFields:
# the string columns below stop accepting NULL, so existing NULL values have
# to become the empty string before the columns turn NOT NULL. The listed
# models are the concrete ones which carry these columns: ConformityCheckRun,
# RemoteMetadata, ServiceMetadata and MetadataRecord are abstract and only
# replicate their fields into their children.

from django.db import migrations

TERMS_OF_USE_FIELDS = [
    'access_constraints',
    'fees',
    'use_limitation',
    'license_source_note',
]

TEXT_FIELDS = {
    'WmsConformityCheckRun': ['report'],
    'LayerConformityCheckRun': ['report'],
    'FeatureTypeConformityCheckRun': ['report'],
    'DatasetMetadataConformityCheckRun': ['report'],
    'WebMapServiceRemoteMetadata': ['remote_content'],
    'LayerRemoteMetadata': ['remote_content'],
    'WebFeatureServiceRemoteMetadata': ['remote_content'],
    'FeatureTypeRemoteMetadata': ['remote_content'],
    'CatalogueServiceRemoteMetadata': ['remote_content'],
    'WebMapService': TERMS_OF_USE_FIELDS,
    'WebFeatureService': TERMS_OF_USE_FIELDS,
    'CatalogueService': TERMS_OF_USE_FIELDS,
    'DatasetMetadataRecord': TERMS_OF_USE_FIELDS,
    'ServiceMetadataRecord': TERMS_OF_USE_FIELDS,
    'ApplicationMetadataRecord': TERMS_OF_USE_FIELDS,
}


def nulls_to_empty(apps, schema_editor):
    for model_name, fields in TEXT_FIELDS.items():
        model = apps.get_model('registry', model_name)
        for field in fields:
            model.objects.filter(**{f'{field}__isnull': True}).update(
                **{field: ''})


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0051_the_audit_diff_counts_the_profile'),
    ]

    operations = [
        migrations.RunPython(nulls_to_empty, migrations.RunPython.noop),
    ]
