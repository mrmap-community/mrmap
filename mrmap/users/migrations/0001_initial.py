# Generated by Django 3.1.7 on 2021-04-19 11:47

import datetime
from django.conf import settings
import django.contrib.auth.models
import django.contrib.auth.tokens
import django.contrib.auth.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from django.utils.timezone import utc
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('service', '0001_initial'),
        ('structure', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='MrMapUser',
            fields=[
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('confirmed_newsletter', models.BooleanField(default=False, verbose_name='I want to sign up for the newsletter')),
                ('confirmed_survey', models.BooleanField(default=False, verbose_name='I want to participate in surveys')),
                ('confirmed_dsgvo', models.DateTimeField(auto_now_add=True, verbose_name='I understand and accept that my data will be automatically processed and securely stored, as it is stated in the general data protection regulation (GDPR).')),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.Group', verbose_name='groups')),
                ('organization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='user_set', to='structure.organization')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.Permission', verbose_name='user permissions')),
            ],
            options={
                'verbose_name': 'User',
                'verbose_name_plural': 'Users',
            },
            managers=[
                ('objects', django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name='UserActivation',
            fields=[
                ('activation_until', models.DateTimeField(default=datetime.datetime(2021, 5, 19, 11, 47, 55, 883098, tzinfo=utc))),
                ('activation_hash', models.CharField(max_length=500, primary_key=True, serialize=False)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            bases=(models.Model, django.contrib.auth.tokens.PasswordResetTokenGenerator),
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created at')),
                ('last_modified_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='Last modified at')),
                ('id', models.UUIDField(default=uuid.uuid4, primary_key=True, serialize=False)),
                ('notify_on_update', models.BooleanField(default=True, help_text='Sends an e-mai if the service has been updated.', verbose_name='Notify on update')),
                ('notify_on_metadata_edit', models.BooleanField(default=True, help_text="Sends an e-mai if the service's metadata has been changed.", verbose_name='Notify on metadata edit')),
                ('notify_on_access_edit', models.BooleanField(default=True, help_text="Sends an e-mai if the service's access has been changed.", verbose_name='Notify on access edit')),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('created_by_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='users_subscription_created', to=settings.AUTH_USER_MODEL, verbose_name='Created by')),
                ('last_modified_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='users_subscription_lastmodified', to=settings.AUTH_USER_MODEL, verbose_name='Last modified by')),
                ('metadata', models.ForeignKey(help_text='Select the service you want to subscribe. When you edit an existing subscription, you can not change this selection.', on_delete=django.db.models.deletion.CASCADE, to='service.metadata', verbose_name='Service')),
                ('owned_by_org', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='users_subscription_owned', to='structure.organization', verbose_name='Owner')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('metadata', 'user')},
            },
        ),
    ]
