"""The migration autodetector which sees the views and the triggers.

Two packages of this deployment integrate with the migration autodetector
and both of them do it so that only their own integration is active:
django-pgviews-redux overrides the ``makemigrations`` and ``migrate``
commands of Django and answers its ``PGViewsAutodetector`` on them, while
django-pgtrigger patches the autodetector of the standard commands when its
app is ready (#1009). The commands of the views win over the patched standard
commands and the patches never reach them, so whichever integration a command
carries, the detection of the other one is silently lost - makemigrations
then answers no operations for the triggers of the registry and a deployment
would be migrated without their maintenance installed while nothing
complains.

This autodetector carries both. It layers the trigger detection of pgtrigger
over the view detection of the views package; the two cooperate because the
views fill their state and generate their operations from it while the
triggers generate theirs from the model options, and neither of them names
what the other one overrides. Django requires the two commands to answer one
and the same autodetector class (``commands.E001``), so it lives here and not
in either command.
"""

from django_pgviews.db.migrations.autodetector import PGViewsAutodetector
from pgtrigger.migrations import MigrationAutodetectorMixin


class ViewsAndTriggersAutodetector(MigrationAutodetectorMixin,
                                   PGViewsAutodetector):
    """The autodetector which detects views and triggers together."""
