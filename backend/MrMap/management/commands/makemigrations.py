"""The makemigrations command of the project.

It carries the autodetector which sees the views of django-pgviews-redux and
the triggers of django-pgtrigger together (see
``MrMap/migration_detection.py``), and it is the command which is found
because ``MrMap`` is listed before ``django_pgviews`` in ``INSTALLED_APPS``
while ``get_commands`` runs the apps in reverse, so the first app which names
a command wins over the later ones (#1009).
"""

from django_pgviews.management.commands.makemigrations import \
    Command as PGViewsMakemigrationsCommand

from MrMap.migration_detection import ViewsAndTriggersAutodetector


class Command(PGViewsMakemigrationsCommand):
    autodetector = ViewsAndTriggersAutodetector
