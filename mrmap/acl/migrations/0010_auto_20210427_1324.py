# Generated by Django 3.1.8 on 2021-04-27 11:24

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('acl', '0009_accesscontrollist_accessible_accesscontrollist'),
    ]

    operations = [
        migrations.RenameField(
            model_name='accesscontrollist',
            old_name='accessible_metadatas',
            new_name='accessible_metadata',
        ),
    ]