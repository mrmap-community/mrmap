"""Moves the object permissions of the services into the tables of their own.

Migration 0021 gives the services a table of their own for their object
permissions, because guardian's shared table names an object by the text of its
primary key and a lookup for a model with a uuid primary key casts that column
for the rows of every model. Guardian answers a model which has such a table
only from it, so the rows a deployment already stored in the shared tables have
to move: without them every service of that deployment would answer as granted
to nobody.

A row naming an object which does not exist stays where it is. The dedicated
table has a real foreign key, the shared one never had one, and
``manage.py clean_orphan_obj_perms`` is the command for those rows.
"""
from django.core.exceptions import ValidationError
from django.db import migrations

#: the app label which holds the dedicated tables this migration fills
APP_LABEL = 'registry'

#: guardian's shared tables, one per kind of actor
SHARED = {
    'user': 'UserObjectPermission',
    'group': 'GroupObjectPermission',
}

#: app label and model of the objects whose permissions move and, for every kind
#: of actor, the name of the actor and the model of the table it moves into
MOVED = [
    ('registry', 'webmapservice', 'user', 'WebMapServiceUserObjectPermission'),
    ('registry', 'webmapservice', 'group', 'WebMapServiceGroupObjectPermission'),
    ('registry', 'webfeatureservice', 'user',
     'WebFeatureServiceUserObjectPermission'),
    ('registry', 'webfeatureservice', 'group',
     'WebFeatureServiceGroupObjectPermission'),
]

#: the rows one statement writes or removes, so that no statement names every
#: permission of a deployment in one list of values
BATCH_SIZE = 500


def content_type(apps, app_label, model):
    """The content type of a model, or None if the deployment never had one"""
    return apps.get_model('contenttypes', 'ContentType').objects.filter(
        app_label=app_label, model=model).first()


def objects_named(target, texts):
    """The texts which name an object of the given model which still exists

    The shared table never had a foreign key, so a row can name an object which
    is gone, or name nothing at all: a text the primary key of the model can not
    read is the same case as a text naming a deleted object.

    Args:
        target: the model whose primary key reads the texts
        texts: the ``object_pk`` values of the rows which want to move

    Returns:
        dict: the primary key of every object named by one of the texts, by the
            text which names it
    """
    named = {}
    for text in texts:
        try:
            named[text] = target._meta.pk.to_python(text)
        except (ValidationError, ValueError):
            continue
    if not named:
        return {}
    existing = set(target.objects.filter(
        pk__in=list(named.values())).values_list('pk', flat=True))
    return {text: pk for text, pk in named.items() if pk in existing}


def delete_in_batches(model, pks):
    """Removes the rows of a model by their primary keys, in batches"""
    for start in range(0, len(pks), BATCH_SIZE):
        model.objects.filter(pk__in=pks[start:start + BATCH_SIZE]).delete()


def forwards(apps, schema_editor):
    """Carries the rows of guardian's shared tables into the dedicated ones"""
    for target_label, target_model, actor, direct_model in MOVED:
        content = content_type(apps, target_label, target_model)
        if content is None:
            continue
        target = apps.get_model(target_label, target_model)
        shared = apps.get_model('guardian', SHARED[actor])
        direct = apps.get_model(APP_LABEL, direct_model)

        granted = list(shared.objects.filter(content_type=content))
        objects = objects_named(target, [row.object_pk for row in granted])
        moved = [row for row in granted if row.object_pk in objects]
        if not moved:
            continue

        direct.objects.bulk_create(
            [direct(**{
                f'{actor}_id': getattr(row, f'{actor}_id'),
                'permission_id': row.permission_id,
                'content_object_id': objects[row.object_pk]})
             for row in moved],
            batch_size=BATCH_SIZE, ignore_conflicts=True)
        delete_in_batches(shared, [row.pk for row in moved])


def backwards(apps, schema_editor):
    """Carries the rows of the dedicated tables back into the shared ones"""
    for target_label, target_model, actor, direct_model in MOVED:
        content = content_type(apps, target_label, target_model)
        if content is None:
            continue
        shared = apps.get_model('guardian', SHARED[actor])
        direct = apps.get_model(APP_LABEL, direct_model)

        granted = list(direct.objects.all())
        if not granted:
            continue
        shared.objects.bulk_create(
            [shared(**{
                f'{actor}_id': getattr(row, f'{actor}_id'),
                'permission_id': row.permission_id,
                'content_type': content,
                'object_pk': row.content_object_id})
             for row in granted],
            batch_size=BATCH_SIZE, ignore_conflicts=True)
        delete_in_batches(direct, [row.pk for row in granted])


class Migration(migrations.Migration):

    dependencies = [
        ('registry', '0021_dedicated_guardian_object_permission_tables'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
