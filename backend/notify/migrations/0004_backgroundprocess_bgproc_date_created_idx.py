"""A kept name, without operations (#1180).

Added the ``bgproc_date_created_idx`` index over ``date_created``; the
regenerated ``0001_initial`` declares it in the model's ``Meta``, so the node
adds nothing now. Its name is what a database which built the index recorded.

The node used to repeat the dependencies on ``contenttypes`` and on the
``django_celery_results`` migration which pinned the index into the graph beside
the ``threads`` field. Both are gone with the package (#1180), which is the
other reason this file had to lose its contents: a dependency line of its own on
the removed app would have kept the graph unloadable without it.

Its name is pinned from behind by ``0005_alter_backgroundprocess_process_type``,
which three applied ``registry`` migrations name as their dependency.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notify', '0003_backgroundprocess_status'),
    ]

    operations = []
