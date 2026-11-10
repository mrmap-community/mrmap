"""A kept name, without operations (#1180).

Added ``status`` and filled it from the state of the ``threads`` relation and
of ``done_at``. The column is created by the regenerated ``0001_initial``, and
the filling cannot and need not run again:

* a new database has no process to fill when this node is reached, so the step
  was always a no-op there;
* a database which applied it recorded this name and is not asked again;
* the lookup itself, ``threads__status__in=[...]``, is a query over the relation
  #1179 retired and the package of #1180 removes, so keeping it would have kept
  the whole point of the removal alive inside the history.

The name is pinned from behind: ``0004`` parents on this node and, through
``0004``, up to ``0005``, so do the three ``registry`` migrations which name
``0005``.

The baseline this leaves behind is the release which carries #1178 and #1179
(#1180, answer 3): a deployment which reaches this chain without having applied
``0003`` gets no ``status`` column from it, ``migrate`` says nothing about that,
and the application then fails on the missing column. Operators check
``showmigrations notify`` for ``0006`` before upgrading, which
``docs/source/development/celery-result-backend.rst`` spells out.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notify', '0002_alter_backgroundprocess_date_created_and_more'),
    ]

    operations = []
