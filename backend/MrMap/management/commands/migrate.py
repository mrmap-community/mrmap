"""The migrate command of the project.

It carries the one autodetector which sees the views of
django-pgviews-redux and the triggers of django-pgtrigger together (see
``MrMap/migration_detection.py``, #1009); Django requires the two commands
to answer one and the same class. See the makemigrations command of this
directory for the rule by which this command is the one that is found.
"""

from django.core.management.commands.migrate import \
    Command as DjangoMigrateCommand

from MrMap.migration_detection import ViewsAndTriggersAutodetector


class Command(DjangoMigrateCommand):
    autodetector = ViewsAndTriggersAutodetector
