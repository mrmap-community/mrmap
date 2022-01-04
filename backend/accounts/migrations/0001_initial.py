# Generated by Django 3.2.9 on 2022-01-04 15:07

import accounts.managers.users
from django.conf import settings
import django.contrib.auth.models
import django.contrib.auth.tokens
import django.contrib.auth.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
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
                ('confirmed_dsgvo', models.DateTimeField(auto_now_add=True, help_text='I understand and accept that my data will be automatically processed and securely stored, as it is stated in the general data protection regulation (GDPR).')),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.Group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.Permission', verbose_name='user permissions')),
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
                ('group_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='auth.group')),
                ('person_name', models.CharField(blank=True, default='', max_length=200, null=True, verbose_name='Contact person')),
                ('email', models.EmailField(blank=True, default='', max_length=100, null=True, verbose_name='E-Mail')),
                ('phone', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Phone')),
                ('facsimile', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Facsimile')),
                ('city', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='City')),
                ('postal_code', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Postal code')),
                ('address_type', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Address type')),
                ('address', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Address')),
                ('state_or_province', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='State or province')),
                ('country', models.CharField(blank=True, default='', max_length=100, null=True, verbose_name='Country')),
                ('description', models.TextField(blank=True, default='', help_text='Describe what this organization representing', null=True, verbose_name='description')),
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
            name='UserActivation',
            fields=[
                ('activation_until', models.DateTimeField()),
                ('activation_hash', models.CharField(max_length=500, primary_key=True, serialize=False)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            bases=(models.Model, django.contrib.auth.tokens.PasswordResetTokenGenerator),
        ),
        migrations.CreateModel(
            name='PublishRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message', models.TextField(blank=True, null=True)),
                ('activation_until', models.DateTimeField(blank=True, null=True)),
                ('is_accepted', models.BooleanField(default=False, verbose_name='accepted')),
                ('from_organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='from_pending_publish_requests', to='accounts.organization', verbose_name='requesting organization')),
                ('to_organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='to_pending_publish_requests', to='accounts.organization', verbose_name='requested organization')),
            ],
            options={
                'verbose_name': 'Pending publish request',
                'verbose_name_plural': 'Pending publish requests',
                'unique_together': {('from_organization', 'to_organization')},
            },
        ),
    ]
