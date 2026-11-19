"""The audit trail of the role system (#741).

Who holds a role, who granted it and what a definition meant are questions an
administrator is asked after the fact. ``RoleDefinition``, ``Role`` and
``RoleMembership`` answer them through ``simple_history``, the same machinery
the registry uses for its records; the permission set of a definition is
tracked in its own table because a tracked many-to-many is not a column of the
row. ``LegacyGroupRetirement`` is not history: it is the record of the legacy
role groups the next migration retires, whose ``Group`` rows are gone with
their grants.
"""


import django.db.models.deletion
import django.utils.timezone
import simple_history.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_organizationgroupobjectpermission_created_at_and_more'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='HistoricalRole',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('is_active', models.BooleanField(default=True, help_text='false for a legacy group which is retired by #741; a retired role grants through its group until it is gone, but takes no new membership', verbose_name='is active')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created at')),
                ('history_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('created_by', models.ForeignKey(blank=True, db_constraint=False, help_text='who created this role; empty when a migration or the bootstrap of a new organization created it', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='created by')),
                ('group', models.ForeignKey(blank=True, db_constraint=False, help_text='the group whose members hold this role; django-guardian and Django resolve its permissions, so nothing else enforces a role', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='auth.group', verbose_name='group')),
                ('history_relation', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, related_name='change_logs', to='accounts.role')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('organization', models.ForeignKey(blank=True, db_constraint=False, help_text='the organization this role belongs to; empty only for a role of PLATFORM scope, which reaches over all organizations', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='accounts.organization', verbose_name='organization')),
                ('role_definition', models.ForeignKey(blank=True, db_constraint=False, help_text='what this role means, from the catalogue of #731', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='accounts.roledefinition', verbose_name='role definition')),
            ],
            options={
                'verbose_name': 'historical role',
                'verbose_name_plural': 'historical roles',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalRoleDefinition',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('slug', models.SlugField(help_text="the machine name of the role, such as 'resource_editor'; code and later issues refer to a role by this name", max_length=100, verbose_name='slug')),
                ('label', models.CharField(help_text='the display name of the role', max_length=200, verbose_name='label')),
                ('description', models.TextField(blank=True, default='', help_text='what the role is for, for the operator reading the role list', verbose_name='description')),
                ('scope', models.CharField(choices=[('PLATFORM', 'Platform'), ('ORGANIZATION', 'Organization')], default='ORGANIZATION', help_text='PLATFORM for roles which reach over all organizations, ORGANIZATION for the roles a member of one organization gets', max_length=20, verbose_name='scope')),
                ('is_builtin', models.BooleanField(default=False, editable=False, help_text='shipped with MrMap: the row is seeded by migration, kept by manage.py sync_role_definitions and cannot be deleted', verbose_name='is builtin')),
                ('is_default', models.BooleanField(default=False, help_text='membership grants this role automatically, once #732 applies roles to memberships', verbose_name='is default')),
                ('is_assignable', models.BooleanField(default=True, help_text='the role is offered in the member picker; platform_admin is not, because holding it is not an ordinary membership', verbose_name='is assignable')),
                ('history_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('history_relation', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, related_name='change_logs', to='accounts.roledefinition')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'historical role definition',
                'verbose_name_plural': 'historical role definitions',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalRoleDefinition_permissions',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('m2m_history_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('history', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, to='accounts.historicalroledefinition')),
                ('permission', models.ForeignKey(blank=True, db_constraint=False, db_tablespace='', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='auth.permission')),
                ('roledefinition', models.ForeignKey(blank=True, db_constraint=False, db_tablespace='', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='accounts.roledefinition')),
            ],
            options={
                'verbose_name': 'HistoricalRoleDefinition_permissions',
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalRoleMembership',
            fields=[
                ('id', models.BigIntegerField(auto_created=True, blank=True, db_index=True, verbose_name='ID')),
                ('granted_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='granted at')),
                ('valid_until', models.DateTimeField(blank=True, default=None, help_text='when the membership stops being valid; revoked by the periodic task of #741', null=True, verbose_name='valid until')),
                ('history_id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('granted_by', models.ForeignKey(blank=True, db_constraint=False, help_text='who added the user to the role; empty for a membership a migration or a bootstrap took over, where no decision is known', null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='granted by')),
                ('history_relation', models.ForeignKey(db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, related_name='change_logs', to='accounts.rolemembership')),
                ('history_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('role', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='accounts.role', verbose_name='role')),
                ('user', models.ForeignKey(blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'verbose_name': 'historical role membership',
                'verbose_name_plural': 'historical role memberships',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='LegacyGroupRetirement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group_pk', models.BigIntegerField(help_text='the primary key the retired auth.Group row had; the row is gone, this names it', unique=True, verbose_name='group pk')),
                ('group_name', models.CharField(help_text='the name the retired group carried, for reading', max_length=150, verbose_name='group name')),
                ('members', models.JSONField(default=list, help_text='the usernames which held the retired group, and where each of them went: adopted into the successor role, or already holding it', verbose_name='members')),
                ('grants', models.JSONField(default=list, help_text='the backup of every guardian grant row deleted with the group: its model, object, permission and the disposition it was reconciled to', verbose_name='grants')),
                ('grants_covered', models.PositiveIntegerField(default=0, editable=False, help_text='how many of those rows the successor role already granted through the facade of #734', verbose_name='grants covered')),
                ('grants_preserved', models.PositiveIntegerField(default=0, editable=False, help_text='how many of those rows were written onto the members who already held them, because no role grants them', verbose_name='grants preserved')),
                ('retired_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='retired at')),
                ('organization', models.ForeignKey(blank=True, help_text='the organization the retired role belonged to', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='retirements', to='accounts.organization', verbose_name='organization')),
                ('role_definition', models.ForeignKey(blank=True, help_text='what the retired role meant, from the catalogue', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='retirements', to='accounts.roledefinition', verbose_name='role definition')),
                ('successor', models.ForeignKey(blank=True, help_text="the active role whose members took the retired group's members and reconciled grants", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='retired_group_records', to='accounts.role', verbose_name='successor role')),
            ],
            options={
                'verbose_name': 'legacy group retirement',
                'verbose_name_plural': 'legacy group retirements',
                'ordering': ['group_pk'],
            },
        ),
    ]
