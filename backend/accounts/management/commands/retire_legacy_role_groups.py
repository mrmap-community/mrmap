"""Retires the legacy per-model role groups, or reports what it does.

``manage.py retire_legacy_role_groups --dry-run`` answers the report of
:func:`accounts.retirement.retire_legacy_role_groups` without writing a row:
which groups would go, who would take their members, and which guardian rows
would be dropped as covered by a role, preserved per user, or lost. It is the
backup AC3 of #741 asks for before an upgrade deletes anything, and it is the
same code the data migration of the same issue runs.

Without ``--dry-run`` the reconciliation is applied. Nothing on this command
is reversible by hand afterwards: the record of what went where is written to
``LegacyGroupRetirement`` first, and that table is what an auditor reads.
"""
from django.apps import apps as global_apps
from django.core.management.base import BaseCommand

from accounts.retirement import retire_legacy_role_groups


class Command(BaseCommand):
    help = (
        "Retire the inactive legacy role groups of an upgraded instance "
        "(#741), or report what that would do with --dry-run.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be retired without writing anything.',
        )

    def handle(self, *args, **options):
        report = retire_legacy_role_groups(
            apps=global_apps, dry_run=options['dry_run'])

        verb = 'Would retire' if options['dry_run'] else 'Retired'
        for plan in report['retired']:
            self.stdout.write('{} {}: {} member(s), {} grant(s)'.format(
                verb, plan['group_name'], len(plan['members']),
                len(plan['grants'])))
            self.stdout.write('    successor: {}'.format(plan['successor']))
            for entry in plan['grants']:
                self.stdout.write('    {} {} -> {}'.format(
                    entry['permission'], entry['object'],
                    entry['disposition']))

        for plan in report['declined']:
            self.stderr.write('Kept {}: {}'.format(
                plan['group_name'], plan['declined']))
        for name in report['skipped']:
            self.stdout.write('Kept {}: an inactive role of the api\'s own '
                              'shape, never a migration\'s'.format(name))

        if not report['retired'] and not report['declined']:
            self.stdout.write(
                'Nothing to retire: no inactive role group on this instance.')
        self.stdout.write(self.style.SUCCESS(
            '{} group(s), {} declined.'.format(
                len(report['retired']), len(report['declined']))))
