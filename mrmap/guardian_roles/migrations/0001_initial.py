# Generated by Django 3.1.7 on 2021-04-19 11:47

import django.contrib.auth.models
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='MetadataGroupObjectPermission',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='MetadataUserObjectPermission',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='ObjectBasedRole',
            fields=[
                ('group_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='auth.group')),
                ('description', models.TextField(help_text='Describe what permissions this role shall grant', verbose_name='Description')),
                ('object_pk', models.CharField(max_length=255, verbose_name='object ID')),
            ],
            options={
                'abstract': False,
            },
            bases=('auth.group', models.Model),
            managers=[
                ('objects', django.contrib.auth.models.GroupManager()),
            ],
        ),
        migrations.CreateModel(
            name='TemplateRole',
            fields=[
                ('name', models.CharField(help_text='The unique name of the role', max_length=60, primary_key=True, serialize=False)),
                ('verbose_name', models.CharField(help_text='The verbose name of the role', max_length=60, verbose_name='Verbose name')),
                ('description', models.TextField(help_text='Describe what permissions this role shall grant', verbose_name='Description')),
                ('permissions', models.ManyToManyField(blank=True, related_name='role_set', to='auth.Permission')),
            ],
        ),
        migrations.CreateModel(
            name='OwnerBasedRole',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.TextField(help_text='Describe what permissions this role shall grant', verbose_name='Description')),
                ('based_template', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='guardian_roles_ownerbasedrole_concrete_template', to='guardian_roles.templaterole')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
