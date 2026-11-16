# Data migration prepared by hand, referenced by the following AlterFields:
# the string columns below stop accepting NULL, so existing NULL values have
# to become the empty string before the columns turn NOT NULL. The listed
# models are the concrete ones which carry these columns: Contact and
# BaseInternalRequest are abstract and only replicate into their children.

from django.db import migrations

TEXT_FIELDS = {
    # the Contact columns and Organization.description all live here
    'Organization': [
        'person_name',
        'email',
        'phone',
        'facsimile',
        'city',
        'postal_code',
        'address_type',
        'address',
        'state_or_province',
        'country',
        'description',
    ],
    'PublishRequest': ['message'],
}


def nulls_to_empty(apps, schema_editor):
    for model_name, fields in TEXT_FIELDS.items():
        model = apps.get_model('accounts', model_name)
        for field in fields:
            model.objects.filter(**{f'{field}__isnull': True}).update(
                **{field: ''})


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_move_generic_object_permissions_to_direct_tables'),
    ]

    operations = [
        migrations.RunPython(nulls_to_empty, migrations.RunPython.noop),
    ]
