"""Retires the legacy per-model role groups (#741 AC3).

Migration 0008 could not delete the ``<Org> <model> Admins`` groups it found on
a running instance: django-guardian's rows point at a ``Group`` by key, so it
left them standing as *inactive* roles and handed the list to this migration.
With the audit trail of 0011 in place - and the record table it creates - the
groups can go: :func:`accounts.retirement.retire_legacy_role_groups` adopts
every member into the active role of the same definition and organization,
classifies each guardian row of the group as covered by that role or preserved
per user, writes the mapping into ``LegacyGroupRetirement`` and only then
deletes role and group.

Three properties this migration keeps:

* **Nothing broadens.** A member is adopted into the role which already means
  what their legacy group meant; an uncovered grant is written only onto the
  people who already held it. The report of every row is in the record table,
  and ``manage.py retire_legacy_role_groups --dry-run`` answers it over a copy
  before an upgrade runs this.
* **Nothing is published.** The anonymous viewer is never a successor, and the
  group of an ``Organization`` - which is an ``auth.Group`` row too - is never
  taken for a legacy one.
* **A group which cannot be proven reconciled stays.** The migration names it
  in the log instead of guessing, because an unrecoverable deletion is worse
  than a stale group, and ``accounts.E005`` keeps reporting it until a person
  decides.

Idempotent by the unique key on the retired group's primary key and by the
selection itself: a second run finds no inactive legacy group left. It cannot
be reversed - the deleted ``Group`` rows and their cascaded grants are gone -
so the reverse is an explicit no-op, and the audit trail of 0011 beside the
record table is what an operator reads after a rollback of the code.
"""

from django.db import migrations

from accounts.retirement import retire_legacy_role_groups


def retire_legacy_groups(apps, schema_editor):
    """Reconcile and delete every legacy per-model role group.

    Args:
        apps: the app registry of this migration
        schema_editor: the editor, never asked: the work runs over the models
            of the migration state and needs no connection of its own
    """
    report = retire_legacy_role_groups(apps=apps)
    for plan in report['declined']:
        print(f"[accounts 0012] kept {plan['group_name']}: "
              f"{plan['declined']}")
    for name in report['skipped']:
        print(f"[accounts 0012] kept {name}: not a legacy per-model group")
    if report['retired']:
        print(f"[accounts 0012] retired {len(report['retired'])} legacy role "
              f"group(s); see accounts_legacygroupretirement for the mapping")


def keep_the_record_of_it(apps, schema_editor):
    """Leaves the database as it is: a retired group cannot be un-retired.

    The role and its ``Group`` are deleted, and the guardian rows of that group
    cascaded away with it; ``LegacyGroupRetirement`` is what remains to say
    what was there. A deployment which needs the old state back restores a
    backup from before this migration - which is what the ``--dry-run`` report
    of the same module is meant to make a decision about, not a guess.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_the_role_tables_are_audited'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(retire_legacy_groups,
                             keep_the_record_of_it),
    ]
