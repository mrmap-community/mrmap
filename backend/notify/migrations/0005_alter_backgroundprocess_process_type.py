"""A kept name, without operations — and a name other apps depend on (#1180).

Added the ``update`` choice to ``process_type``; the regenerated
``0001_initial`` declares the current choices, so the node adds nothing.

The reason this particular name is load-bearing beyond its own database:
``registry/0014``, ``registry/0020`` and ``registry/0037`` each name
``('notify', '0005_alter_backgroundprocess_process_type')`` as a dependency, and
an applied registry migration may not be rewritten. So the node stays exactly
under this name, empty, and the ``registry`` history resolves untouched. Same
keep-your-number doctrine as elsewhere in the migration ledger, only inverted:
here ``notify`` keeps the name and its neighbours keep their dependency on it.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('notify', '0004_backgroundprocess_bgproc_date_created_idx'),
    ]

    operations = []
