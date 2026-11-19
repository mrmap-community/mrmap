"""The scheduled work of the role system (#741).

One sweep lives here, on the same footing as the housekeeping of ``notify``:
beat reads its schedule out of the database and ``accounts/apps.py`` writes
the row, so a deployment which re-schedules it over the api keeps what it
chose.

Why a sweep at all: a membership whose ``valid_until`` has passed is not a
valid grant, and the facade of #734 already refuses it on the two role axes.
But the person is still in the group of the role, and a guardian grant of that
group - the view/change/delete rows the creation bootstrap of #732/#733 wrote -
keeps reaching them until the membership row is gone. The facade says so in its
own module docstring; this task is the half which closes the gap, and the
acceptance of #741 ("an expired membership stops granting on the next request")
is only true with it.
"""

from logging import Logger

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from extras.tasks import SingletonTask
from MrMap import celery_queues

logger: Logger = settings.ROOT_LOGGER

#: the shape of the ``history_change_reason`` of a row this sweep deleted. An
#: audit which cannot tell "the schedule revoked her" from "an administrator
#: revoked her" answers the question of #741 wrongly, so the reason goes into
#: the audit row and not only into the log line. Bounded: the column is a
#: ``CharField`` of 100 characters, and the timestamp below is 16 of them.
EXPIRY_REASON = "membership expired: valid_until %s passed"

#: how the moment of the reason is spelled - minute precision, in the
#: deployment's timezone, which is what an operator reading the audit expects
EXPIRY_REASON_TIME_FORMAT = "%Y-%m-%d %H:%M %Z"


def expiry_reason(membership) -> str:
    """The audit reason naming the moment ``membership`` expired.

    The timestamp is the row's own, never the clock of the sweep: an audit row
    says when the grant ended, not when a worker happened to run.
    """
    return EXPIRY_REASON % timezone.localtime(
        membership.valid_until).strftime(EXPIRY_REASON_TIME_FORMAT)


@shared_task(queue=celery_queues.DB_ROUTINES, bind=True, base=SingletonTask)
def revoke_expired_role_memberships(self, *args, **kwargs):
    """Takes the role of every membership whose validity has passed (#741).

    Runs as a singleton on ``db-routines`` like the other housekeeping: two
    sweeps over the same rows have nothing to add to each other, and the sweep
    is cheap enough that an overlap would only be noise.

    Deleting the membership is the revocation: ``RoleMembership.delete()`` takes
    the user out of the group of the role, which is what withdraws every object
    grant that group carried, and drops the cached permission strings of the
    user (#734) - so the next request of that person is answered without the
    role, which is the acceptance of this issue. Each row goes in its own
    transaction, because a membership which left its user in a group would be
    the stale grant this sweep exists to remove; a run which dies half-way is
    re-run by the next fire and revokes what is still standing.

    The audit trail of #741 is kept intact: the row is deleted through the
    model, so simple-history writes the ``-`` row of the membership with the
    reason ``expiry_reason`` states.
    """
    from accounts.models.roles import RoleMembership

    now = timezone.now()
    revoked = []
    for membership in RoleMembership.objects.for_revocation_task(now=now):
        # the identity of the grant, read before the delete: afterwards the
        # instance carries no role any more
        granted = f"{membership.user} @ {membership.role}"
        reason = expiry_reason(membership)
        with transaction.atomic():
            membership._change_reason = reason
            # orm-lint: ignore MRMAP-ORM-004 -- one delete per expired row is the design, not an oversight: the row is its own transaction, so a sweep which dies half-way leaves nobody in a group it should have left, and it is deleted through the model so simple-history writes the ``-`` row of that one membership with its own reason -- a bulk delete answers both statements wrongly
            membership.delete()
        revoked.append((granted, reason))

    for granted, reason in revoked:
        logger.info(
            "Role membership revoked: %s (%s).", granted, reason)
    if revoked:
        logger.info(
            "Role memberships: %s expired membership(s) revoked as of %s.",
            len(revoked), now.isoformat())
    return {"revoked": len(revoked), "as_of": now.isoformat()}
