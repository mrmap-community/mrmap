# the profile resource of the metadata editor (#1240): the model and the
# seeded `iso19139-generic` row. The link of the records to it follows in
# 0050, after this migration has created the row they default to.

import uuid

from django.db import migrations, models

#: the fixed pk of the generic profile; `registry.models.metadata` holds the
#: same constant as the model default of a record's `profile` — change one,
#: change the other
GENERIC_ISO19139_PROFILE_PK = uuid.UUID("0180721f-bf34-4281-b367-648a74dd8ff9")

#: the sections of the generic profile, in the order the editor's section
#: rail renders them (#1245). The field names are the names the record
#: resource answers them under — the editor matches them against the
#: OpenAPI properties, so they are camelCased like those. `requirement`
#: follows the ISO 19139 schema on its unconditional mandatory elements
#: (title, abstract, keyword, contact, language, characterSet); everything
#: the schema leaves free and GDI-DE-style profiles commonly ask for is
#: `recommended`, the rest `optional`. Read-only fields have no place here:
#: the editor takes them from the schema's readOnly marker, not from a
#: section. This grouping is the v1 generic view of the fields the mapper
#: configs map; `iso19139-gdi-de` will carry its own as data.
GENERIC_ISO19139_SECTIONS = [
    {
        "id": "identification",
        "label": "Identification",
        "fields": [
            {"field": "title", "requirement": "mandatory"},
            {"field": "abstract", "requirement": "mandatory"},
            {"field": "keywords", "requirement": "mandatory"},
            {"field": "metadataContact", "requirement": "mandatory"},
            {"field": "languages", "requirement": "mandatory"},
            {"field": "categories", "requirement": "recommended"},
            {"field": "datasetContact", "requirement": "recommended"},
            {"field": "applicationContact", "requirement": "recommended"},
            {"field": "code", "requirement": "recommended"},
            {"field": "codeSpace", "requirement": "recommended"},
            {"field": "updateFrequencyCode", "requirement": "recommended"},
            {"field": "equivalentScale", "requirement": "optional"},
            {"field": "groundRes", "requirement": "optional"},
        ],
    },
    {
        "id": "extent",
        "label": "Spatial and temporal extent",
        "fields": [
            {"field": "boundingGeometry", "requirement": "recommended"},
            {"field": "referenceSystems", "requirement": "recommended"},
            {"field": "timeExtents", "requirement": "optional"},
        ],
    },
    {
        "id": "distribution",
        "label": "Distribution and use",
        "fields": [
            {"field": "accessConstraints", "requirement": "recommended"},
            {"field": "useLimitation", "requirement": "recommended"},
            {"field": "fees", "requirement": "optional"},
            {"field": "licence", "requirement": "optional"},
            {"field": "licenseSourceNote", "requirement": "optional"},
        ],
    },
    {
        "id": "quality",
        "label": "Data quality",
        "fields": [
            {"field": "charset", "requirement": "mandatory"},
            {"field": "lineageStatement", "requirement": "optional"},
        ],
    },
]


def seed_generic_profile(apps, schema_editor):
    MetadataProfile = apps.get_model("registry", "MetadataProfile")
    # nothing to update on a re-run: the row is seeded once per database, its
    # content belongs to this migration; later profile content arrives in
    # later migrations or over the api
    MetadataProfile.objects.get_or_create(
        pk=GENERIC_ISO19139_PROFILE_PK,
        defaults={
            "name": "iso19139-generic",
            "label": "Generic",
            "sections": GENERIC_ISO19139_SECTIONS,
            # the structural rules are filled by #1243; the field carries
            # them from the first row on
            "rules": [],
        },
    )


def unseed_generic_profile(apps, schema_editor):
    MetadataProfile = apps.get_model("registry", "MetadataProfile")
    MetadataProfile.objects.filter(pk=GENERIC_ISO19139_PROFILE_PK).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0048_merge_20261114'),
    ]

    operations = [
        migrations.CreateModel(
            name='MetadataProfile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(help_text="the machine name of the profile, such as 'iso19139-generic'", max_length=100, unique=True, verbose_name='name')),
                ('label', models.CharField(help_text='the display name of the profile, which the editor renders in its header', max_length=255, verbose_name='label')),
                ('sections', models.JSONField(blank=True, default=list, help_text='the ordered sections of the editor: the fields each section groups and the mandatory/recommended flag of every field', verbose_name='sections')),
                ('rules', models.JSONField(blank=True, default=list, help_text='the ISO structural rules which are validated on save (#1243); attribute constraints keep riding the OpenAPI schema (Q1 option C on #1243)', verbose_name='rules')),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.RunPython(
            seed_generic_profile,
            unseed_generic_profile,
        ),
    ]
