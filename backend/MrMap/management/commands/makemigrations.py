"""The makemigrations command of the project.

It carries the autodetector which sees the views of django-pgviews-redux and
the triggers of django-pgtrigger together (see
``MrMap/migration_detection.py``), and it is the command which is found
because ``MrMap`` is listed before ``django_pgviews`` in ``INSTALLED_APPS``
while ``get_commands`` runs the apps in reverse, so the first app which names
a command wins over the later ones (#1009). The command of the views package
adds nothing to Django's but its own autodetector, so this builds on the
Django command directly and names the combined one.
"""

from django.core.management.base import BaseCommand
from django.core.management.commands.makemigrations import \
    Command as DjangoMakeMigrationsCommand

from MrMap.migration_detection import ViewsAndTriggersAutodetector


# BaseCommand is already an ancestor of the Django command; it is listed
# explicitly because static analyzers do not see the inheritance through the
# imported class. Listing it cannot change anything: the MRO stays
# (Command, DjangoMakeMigrationsCommand, BaseCommand, object).
class Command(DjangoMakeMigrationsCommand, BaseCommand):
    autodetector = ViewsAndTriggersAutodetector
