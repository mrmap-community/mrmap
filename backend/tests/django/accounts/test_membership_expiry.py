"""The sweep which revokes an expired role membership (#741 AC4).

``valid_until`` says when a grant ends. The facade of #734 refuses an expired
membership on its two role axes, but the person is still *in the group of the
role* - and a guardian grant of that group, the rows the bootstrap of #732/#733
wrote, keeps reaching them until the membership row is gone. The sweep of
``accounts.tasks`` is the half which closes that gap, and this module asks the
acceptance's own sentence: **an expired membership stops granting on the next
request**.

The clock is named rather than waited for: the test states the moment the sweep
judges at, which is also how an operator reads the code - ``valid_until`` is
compared against a clock, never against a guess of today.

The object the grants are asked over is an ``Organization``: the bootstrap
grants ``can_publish_for_organization`` onto the group of the organization's
default role, so the right is an object grant of a role group and the whole
chain - membership, group, guardian row - is what the sweep withdraws.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django_celery_beat.models import PeriodicTask

from accounts.apps import MEMBERSHIP_EXPIRY_TASK_NAME
from accounts.models.groups import Organization
from accounts.models.roles import Role, RoleDefinition, RoleMembership
from accounts.tasks import (EXPIRY_REASON, EXPIRY_REASON_TIME_FORMAT,
                            expiry_reason, revoke_expired_role_memberships)

PUBLISH_PERM = "accounts.can_publish_for_organization"


class MembershipExpiryTest(TestCase):
    """One member, one membership with a date, and the sweep over both."""

    def setUp(self):
        self.organization = Organization.objects.create(name="Expiry Org")
        self.member = get_user_model().objects.create_user(
            username="expiring", password="x")
        # the default role of the organization: the bootstrap grants
        # can_publish_for_organization onto exactly this role's group
        default = RoleDefinition.objects.get(is_default=True)
        self.role = Role.objects.for_org(
            self.organization).with_definition(default.slug).get()
        self.role.add_member(self.member)

    def expire_at(self, moment):
        """Set the membership's own end date."""
        membership = self.role.memberships.get(user=self.member)
        membership.valid_until = moment
        membership.save()
        return membership

    def sweep_at(self, moment):
        """Run the sweep as if the clock read ``moment``.

        ``run()`` is the body of the task: the singleton lock it shares with the
        worker is a database advisory lock and is tested by the lock's own
        module, not by the revocation which happens inside it.
        """
        with patch("accounts.tasks.timezone.now", return_value=moment):
            return revoke_expired_role_memberships.run()

    def test_an_expired_membership_stops_granting(self):
        """AC4: the next request after the sweep answers without the role.

        Before: the member publishes, because the group of their role holds the
        object grant. After the sweep: the membership is gone, the member is out
        of the group - which is what withdraws every grant that group carried -
        and the cached permission strings of #734 are dropped, so the next
        request is answered from the database and not from a stale cache.
        """
        self.assertTrue(self.member.has_perm(PUBLISH_PERM, self.organization),
                        "the fixture grants nothing to withdraw")

        self.expire_at(timezone.now() - timedelta(days=1))
        self.sweep_at(timezone.now())

        self.assertFalse(RoleMembership.objects.filter(
            role=self.role, user=self.member).exists())
        self.assertNotIn(self.member, self.role.group.user_set.all())
        self.member = get_user_model().objects.get(pk=self.member.pk)
        self.assertFalse(
            self.member.has_perm(PUBLISH_PERM, self.organization),
            "an expired membership still grants what its role group carried")

    def test_the_sweep_judges_by_the_clock_it_runs_at(self):
        """A membership which is not yet valid is nobody's business yet.

        Both directions are pinned with the same named moment: a date which has
        not passed keeps the grant, and the same row is revoked once the clock
        passes it - which is the only honest way to test a date field.
        """
        now = timezone.now()
        self.expire_at(now + timedelta(days=1))

        self.sweep_at(now)
        self.assertTrue(RoleMembership.objects.filter(
            role=self.role, user=self.member).exists(),
            "a membership which had not expired yet was revoked")
        self.assertTrue(self.member.has_perm(PUBLISH_PERM, self.organization))

        self.sweep_at(now + timedelta(days=2))
        self.assertFalse(RoleMembership.objects.filter(
            role=self.role, user=self.member).exists())

    def test_a_membership_without_a_date_never_expires(self):
        """``valid_until`` is optional: an open-ended grant is the normal case.

        A sweep which read ``NULL`` as "expired" would empty every organization
        on its first fire.
        """
        self.sweep_at(timezone.now() + timedelta(days=365))

        self.assertTrue(RoleMembership.objects.filter(
            role=self.role, user=self.member).exists())

    def test_the_audit_row_names_the_expiry_as_the_reason(self):
        """An expiry is told apart from a revocation by a person.

        The row is deleted through the model, so the trail of #741 keeps the
        ``-`` row - and the reason carries the moment the grant ended, which is
        the date an auditor asks, not the moment a worker happened to run.
        """
        membership = self.expire_at(timezone.now() - timedelta(days=1))
        reason = expiry_reason(membership)

        summary = self.sweep_at(timezone.now())

        self.assertEqual(summary["revoked"], 1)
        # the type of the row, not its timestamp, is what identifies it: the
        # grant and its revocation can share a ``history_date``
        deletions = RoleMembership.change_log.filter(
            user=self.member, history_type="-")
        self.assertEqual(
            deletions.count(), 1, "the sweep deleted without an audit row")
        self.assertEqual(deletions.get().history_change_reason, reason)
        self.assertIn("membership expired", reason)
        self.assertLessEqual(len(reason), 100,
                             "the reason no longer fits its column")

    def test_a_second_sweep_revokes_nothing(self):
        """The work is idempotent, so a re-run and a retry are the same call."""
        self.expire_at(timezone.now() - timedelta(days=1))
        self.sweep_at(timezone.now())

        summary = self.sweep_at(timezone.now())

        self.assertEqual(summary["revoked"], 0)

    def test_the_sweep_is_scheduled_by_the_upgrade(self):
        """The field means what it says only with the row of beat.

        ``accounts/apps.py`` writes the ``PeriodicTask`` on ``post_migrate``,
        keyed by its name - so an upgrade schedules the revocation without an
        operator switching it on, and a deployment which re-scheduled it over
        the api keeps what it chose.
        """
        row = PeriodicTask.objects.filter(
            name=MEMBERSHIP_EXPIRY_TASK_NAME).first()

        self.assertIsNotNone(
            row, "the sweep of expired memberships is not scheduled: the "
                 "upgrade leaves valid_until a field which grants forever")
        self.assertEqual(
            row.task, "accounts.tasks.revoke_expired_role_memberships")
        self.assertEqual(row.crontab.minute, "50")


class ExpiryReasonTest(TestCase):
    """The shape of the reason, which lives in a column of 100 characters."""

    class _Membership:
        def __init__(self, moment):
            self.valid_until = moment

    def test_the_reason_names_the_moment_the_grant_ended(self):
        """Minute precision in the deployment's timezone, never a raw UTC iso."""
        # named in the deployment's own timezone: django.utils.timezone
        # stopped re-exporting ``datetime`` and ``utc``, and a naive local
        # moment made aware is what the docstring of the reason promises
        moment = timezone.make_aware(datetime(2026, 11, 18, 14, 30))

        stamped = timezone.localtime(moment).strftime(
            EXPIRY_REASON_TIME_FORMAT)

        reason = expiry_reason(self._Membership(moment))

        self.assertEqual(reason, EXPIRY_REASON % stamped)
        self.assertLessEqual(len(reason), 100,
                             "a reason which no longer fits its column would "
                             "be truncated by the database, silently")
