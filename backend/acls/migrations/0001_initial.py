# Generated by Django 3.2.7 on 2021-11-19 13:10

from django.db import migrations, models
import django.db.models.deletion
import extras.models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccessControlList',
            fields=[
                ('group_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, to='auth.group')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('description', models.CharField(blank=True, help_text='Describe what this acls shall allow.', max_length=256, null=True, verbose_name='Description')),
                ('default_acl', models.BooleanField(default=False, editable=False)),
                ('organization_admin', models.BooleanField(default=False, editable=False)),
                ('accessible_accesscontrollists', models.ManyToManyField(blank=True, help_text="Select which acls's shall be accessible with the configured permissions.", related_name='_acls_accesscontrollist_accessible_accesscontrollists_+', to='acls.AccessControlList', verbose_name='Accessible access control lists')),
            ],
            options={
                'verbose_name': 'Access Control List',
                'verbose_name_plural': 'Access Control Lists',
            },
            bases=(extras.models.GenericModelMixin, 'auth.group', models.Model),
        ),
    ]
