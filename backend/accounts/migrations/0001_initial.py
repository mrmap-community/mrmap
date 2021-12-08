# Generated by Django 3.2.7 on 2021-12-03 10:12

import os
import uuid

import accounts.managers.users
import django.contrib.auth.models
import django.contrib.auth.tokens
import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
import extras.models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    def generate_superuser(apps, schema_editor):

        superuser = get_user_model().objects.create_superuser(
            username=os.environ.get("MRMAP_USER"),
            password=os.environ.get("MRMAP_PASSWORD")
        )
        superuser.is_active = True
        superuser.save()

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('password', models.CharField(
                    max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(
                    blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False,
                 help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.',
                 max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('first_name', models.CharField(blank=True,
                 max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True,
                 max_length=150, verbose_name='last name')),
                ('email', models.EmailField(blank=True,
                 max_length=254, verbose_name='email address')),
                ('is_staff', models.BooleanField(default=False,
                 help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(
                    default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(
                    default=django.utils.timezone.now, verbose_name='date joined')),
                ('id', models.UUIDField(default=uuid.uuid4,
                 editable=False, primary_key=True, serialize=False)),
                ('confirmed_newsletter', models.BooleanField(default=False,
                 verbose_name='I want to sign up for the newsletter')),
                ('confirmed_survey', models.BooleanField(default=False,
                 verbose_name='I want to participate in surveys')),
                ('confirmed_dsgvo', models.DateTimeField(auto_now_add=True,
                 help_text='I understand and accept that my data will be automatically processed and securely stored, as it is stated in the general data protection regulation (GDPR).')),
            ],
            options={
                'verbose_name': 'User',
                'verbose_name_plural': 'Users',
            },
            managers=[
                ('objects', accounts.managers.users.CustomUserManager()),
            ],
        ),
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('group_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE,
                 parent_link=True, primary_key=True, serialize=False, to='auth.group')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True,
                 help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True,
                 help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('person_name', models.CharField(blank=True, default='',
                 max_length=200, null=True, verbose_name='Contact person')),
                ('email', models.EmailField(blank=True, default='',
                 max_length=100, null=True, verbose_name='E-Mail')),
                ('phone', models.CharField(blank=True, default='',
                 max_length=100, null=True, verbose_name='Phone')),
                ('facsimile', models.CharField(blank=True, default='',
                 max_length=100, null=True, verbose_name='Facsimile')),
                ('city', models.CharField(blank=True, default='',
                 max_length=100, null=True, verbose_name='City')),
                ('postal_code', models.CharField(blank=True, default='',
                 max_length=100, null=True, verbose_name='Postal code')),
                ('address_type', models.CharField(blank=True, default='',
                 max_length=100, null=True, verbose_name='Address type')),
                ('address', models.CharField(blank=True, default='',
                 max_length=100, null=True, verbose_name='Address')),
                ('state_or_province', models.CharField(blank=True, default='',
                 max_length=100, null=True, verbose_name='State or province')),
                ('country', models.CharField(blank=True, default='',
                 max_length=100, null=True, verbose_name='Country')),
                ('description', models.TextField(blank=True, default='',
                 help_text='Describe what this organization representing', null=True, verbose_name='description')),
            ],
            options={
                'verbose_name': 'Organization',
                'verbose_name_plural': 'Organizations',
                'ordering': ['name'],
                'permissions': [('can_publish_for_organization', 'Can publish for this organization')],
            },
            bases=('auth.group', models.Model),
            managers=[
                ('objects', django.contrib.auth.models.GroupManager()),
            ],
        ),
        migrations.CreateModel(
            name='PublishRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True,
                 primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True,
                 help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True,
                 help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('message', models.TextField(blank=True, null=True)),
                ('activation_until', models.DateTimeField(blank=True, null=True)),
                ('is_accepted', models.BooleanField(
                    default=False, verbose_name='accepted')),
            ],
            options={
                'verbose_name': 'Pending publish request',
                'verbose_name_plural': 'Pending publish requests',
            },
        ),
        migrations.CreateModel(
            name='UserActivation',
            fields=[
                ('activation_until', models.DateTimeField()),
                ('activation_hash', models.CharField(
                    max_length=500, primary_key=True, serialize=False)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            bases=(models.Model,
                   django.contrib.auth.tokens.PasswordResetTokenGenerator),
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True,
                 help_text='The timestamp of the creation date of this object.', verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True,
                 help_text='The timestamp of the last modification of this object', verbose_name='Last modified at')),
                ('id', models.UUIDField(default=uuid.uuid4,
                 primary_key=True, serialize=False)),
                ('notify_on_update', models.BooleanField(
                    default=True, help_text='Sends an e-mai if the service has been updated.', verbose_name='Notify on update')),
                ('notify_on_metadata_edit', models.BooleanField(
                    default=True, help_text="Sends an e-mai if the service's metadata has been changed.", verbose_name='Notify on metadata edit')),
                ('notify_on_access_edit', models.BooleanField(
                    default=True, help_text="Sends an e-mai if the service's access has been changed.", verbose_name='Notify on access edit')),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('created_by_user', models.ForeignKey(blank=True, editable=False, help_text='The user who has created this object.', null=True,
                 on_delete=django.db.models.deletion.SET_NULL, related_name='accounts_subscription_created_by_user', to=settings.AUTH_USER_MODEL, verbose_name='Created by')),
                ('last_modified_by', models.ForeignKey(blank=True, editable=False, help_text='The last user who has modified this object.', null=True,
                 on_delete=django.db.models.deletion.SET_NULL, related_name='accounts_subscription_last_modified_by', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by')),
                ('owner', models.ForeignKey(blank=True, editable=False, help_text='The organization which is the owner of this object.', null=True,
                 on_delete=django.db.models.deletion.SET_NULL, related_name='accounts_subscription_owner', to='auth.group', verbose_name='Owner')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            bases=(extras.models.GenericModelMixin, models.Model),
        ),
        migrations.RunPython(generate_superuser),
    ]
