"""The structural rules of the generic iso19139 profile.

The profile of `0004` came with an empty rule list: the rules validate the
harvested document against the shape the mapper expects, and until they were
written down the profile could only describe its sections. Every `assert` below
is an XPath 1.0 boolean over the whole document; the shape they check is defined
by `registry/mappers/rules.py`, GDI-DE and INSPIRE will carry their own as data.

Carried over from the previous chain
(`registry/0052_the_generic_profile_names_its_rules.py`) when the migration
history was regenerated from the models -- the constants and both functions are
that file's text, only its dependencies moved.
"""

import uuid

from django.db import migrations


#: the fixed pk of the generic profile; `registry.models.metadata` and
#: migration 0049 hold the same constant - change one, change the others
GENERIC_ISO19139_PROFILE_PK = uuid.UUID("0180721f-bf34-4281-b367-648a74dd8ff9")

#: the v1 rules. Every `assert` is an XPath 1.0 boolean over the whole
#: document in the prefix-independent local-name() form (#1242 documents
#: that a document may bind the ISO namespaces to any prefix; the browser
#: evaluates the very same string for #1245). The mandatory presence family
#: mirrors the `mandatory` markers of the sections seeded by 0049 - one
#: reading of the ISO 19139 obligations, not two. `dateStamp` grades as a
#: warning: it is readOnly on the record (#1240), so a curator can not fix
#: its absence through the editor and a blocker would lock the record out
#: of every save. The contact-name rule states the ISO 19115 constraint on
#: CI_ResponsibleParty - at least one of organisation, individual or
#: position name - which a mapped contact write can repair.
GENERIC_ISO19139_RULES = [
    {
        "id": "iso19139-title",
        "family": "iso19139",
        "severity": "error",
        "field": "title",
        "assert": ("count(//*[local-name()='MD_Metadata']"
                   "/*[local-name()='identificationInfo']"
                   "//*[local-name()='title'][normalize-space()]) > 0"),
        "message": ("The identification section must carry a title "
                    "(gmd:citation/gmd:title)."),
    },
    {
        "id": "iso19139-abstract",
        "family": "iso19139",
        "severity": "error",
        "field": "abstract",
        "assert": ("count(//*[local-name()='MD_Metadata']"
                   "/*[local-name()='identificationInfo']"
                   "//*[local-name()='abstract'][normalize-space()]) > 0"),
        "message": ("The identification section must carry an abstract "
                    "(gmd:abstract)."),
    },
    {
        "id": "iso19139-keyword",
        "family": "iso19139",
        "severity": "error",
        "field": "keywords",
        "assert": ("count(//*[local-name()='MD_Metadata']"
                   "/*[local-name()='identificationInfo']"
                   "//*[local-name()='keyword'][normalize-space()]) > 0"),
        "message": ("The identification section must name at least one "
                    "keyword (gmd:descriptiveKeywords/gmd:keyword)."),
    },
    {
        "id": "iso19139-metadata-contact",
        "family": "iso19139",
        "severity": "error",
        "field": "metadata_contact",
        "assert": ("count(//*[local-name()='MD_Metadata']"
                   "/*[local-name()='contact']"
                   "/*[local-name()='CI_ResponsibleParty']) > 0"),
        "message": ("The metadata must name a responsible party "
                    "(gmd:contact/gmd:CI_ResponsibleParty)."),
    },
    {
        "id": "iso19139-language",
        "family": "iso19139",
        "severity": "error",
        "field": "languages",
        "assert": ("count(//*[local-name()='MD_Metadata']"
                   "/*[local-name()='language']"
                   "[*[@codeListValue or normalize-space()]]) > 0"),
        "message": ("The metadata must state its language "
                    "(gmd:language with a language code)."),
    },
    {
        "id": "iso19139-characterset",
        "family": "iso19139",
        "severity": "error",
        "field": "charset",
        "assert": ("count(//*[local-name()='MD_Metadata']"
                   "/*[local-name()='characterSet']"
                   "[*[@codeListValue or normalize-space()]]) > 0"),
        "message": ("The metadata must state its character encoding "
                    "(gmd:characterSet)."),
    },
    {
        "id": "iso19139-contact-name",
        "family": "iso19139",
        "severity": "error",
        "field": "metadata_contact",
        "assert": (
            "count(//*[local-name()='MD_Metadata']"
            "/*[local-name()='contact']"
            "/*[local-name()='CI_ResponsibleParty']"
            "[not(*[local-name()='organisationName'][normalize-space()])"
            " and not(*[local-name()='individualName'][normalize-space()])"
            " and not(*[local-name()='positionName'][normalize-space()])])"
            " = 0"),
        "message": ("A named responsible party must carry at least one of "
                    "organisation, individual or position name (ISO 19115 "
                    "constraint on CI_ResponsibleParty)."),
    },
    {
        "id": "iso19139-date-stamp",
        "family": "iso19139",
        "severity": "warning",
        "field": "date_stamp",
        "assert": ("count(//*[local-name()='MD_Metadata']"
                   "/*[local-name()='dateStamp'][normalize-space() or *])"
                   " > 0"),
        "message": ("The metadata header should carry a date stamp "
                    "(gmd:dateStamp); a record without one can not be "
                    "dated against a re-harvest."),
    },
]


def set_generic_rules(apps, schema_editor):
    MetadataProfile = apps.get_model("registry", "MetadataProfile")
    # the seeded row of 0049 is the only row this migration touches, and it
    # fills it unconditionally: the content belongs to this migration the
    # same way the sections belong to 0049. A database without the seeded
    # row (a test database that truncated it) has nothing to fill - the
    # seed's own get_or_create posture, not an error.
    MetadataProfile.objects.filter(
        pk=GENERIC_ISO19139_PROFILE_PK).update(rules=GENERIC_ISO19139_RULES)


def clear_generic_rules(apps, schema_editor):
    MetadataProfile = apps.get_model("registry", "MetadataProfile")
    MetadataProfile.objects.filter(
        pk=GENERIC_ISO19139_PROFILE_PK).update(rules=[])


class Migration(migrations.Migration):

    dependencies = [
        ("registry", "0004_the_generic_metadata_profile_is_seeded"),
    ]

    operations = [
        migrations.RunPython(
            set_generic_rules,
            reverse_code=clear_generic_rules,
        ),
    ]
