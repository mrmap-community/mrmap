"""The generic iso19139 profile, seeded rather than migrated in as a fixture.

The metadata editor (#1240) renders the sections and the structural rules of a
record from a `MetadataProfile` row, and every record created by an import or
through the api defaults to the one seeded here -- `MetadataProfile.generic()`
looks it up by the fixed pk below, which `registry.models.metadata` holds as the
model default of a record's `profile`. Change one, change the other.

The row is data, so it is a data migration: the table itself comes from the
models. Carried over from the previous chain
(`registry/0049_the_profile_of_metadata_is_data.py`) when the migration history
was regenerated from the models -- the constants and both functions are that
file's text, only its dependencies moved.
"""

import uuid

from django.db import migrations


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
        ("registry", "0003_the_initial_data_is_seeded"),
    ]

    operations = [
        migrations.RunPython(
            seed_generic_profile,
            unseed_generic_profile,
        ),
    ]
