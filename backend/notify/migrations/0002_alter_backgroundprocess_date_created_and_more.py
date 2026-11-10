"""A kept name, without operations (#1180).

Altered ``date_created`` and ``date`` from ``auto_now_add`` to a plain
``default=now``. The regenerated ``0001_initial`` creates both the way the
alteration left them, so there is nothing to do here.

The name stays because the chain still stands on it: ``0003`` parents on this
node, ``0004`` on ``0003``, ``0005`` on ``0004``, and three applied ``registry``
migrations name ``0005``. A recorded name which disappears from disk is passed
over in silence, so nothing would complain about *this* database; what breaks is
the graph, which raises ``NodeNotFoundError`` for the child of a missing parent.
Removing this file would therefore fail the migration of every database which
has ``registry`` applied, and it would rewrite what the ledger of an applied
migration means - which history does not do. See ``0001_initial`` for why the
history was regenerated at all.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notify', '0001_initial'),
    ]

    operations = []
