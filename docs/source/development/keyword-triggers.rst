============================================
The keyword maintenance triggers of records
============================================

A searchable metadata record answers its keywords from the ``keywords_list``
column of its own row. The column cannot be a generated column because its
value aggregates the keywords *relation* of the record, so the database keeps
it honest with three kinds of triggers:

``*_keywords_list_sync``
    ``AFTER INSERT OR UPDATE OR DELETE`` on the keywords relation of every
    maintained record type. Every write of the relation -- the orm, a bulk
    ``.set()``, plain sql -- is answered with the aggregate the relation says.

``*_keywords_list_keep``
    ``BEFORE UPDATE`` on every maintained record table. A write of a *record
    row* which brings an array it never read (a fixture, a built instance)
    gets the value of the relation instead. Being a BEFORE trigger is what
    lets the stored ``search_vector`` compute from the array which is really
    written.

``keyword_sync_to_metadatarecords``
    ``AFTER UPDATE OF keyword`` on ``registry_keyword``. A rename is the one
    change which does not pass through a keywords relation, so it is fanned
    out over the records holding the keyword.

These rules were introduced by the registry migrations ``0021``, ``0024`` and
``0033`` as hand written ``CREATE FUNCTION`` / ``CREATE TRIGGER`` statements.
Since #1009 they are managed by `django-pgtrigger
<https://django-pgtrigger.readthedocs.io/>`_: the statements moved to
``backend/registry/triggers.py``, the migration
``0039_the_keyword_maintenance_is_managed_by_pgtrigger`` transferred the
database objects to the package, and a change of a rule now arrives as a
reviewable migration operation. The aggregate inside all of them carries the
empty array of the widened element type, the one thing ``0035`` (#1075) answered
differently on the statements of ``0021``.


Working with the triggers
=========================

The definitions live in ``backend/registry/triggers.py`` and are registered on
their models when the app registry is ready (``registry/apps.py`` imports the
module). To change what a trigger does, edit its class there and run::

    python manage.py makemigrations registry

The autodetector compares the registered triggers with the migration state and
writes a ``pgtrigger.migrations.AddTrigger`` / ``RemoveTrigger`` operation. To
see what the database holds::

    python manage.py pgtrigger ls

Three facts matter when reading or extending this:

*   A trigger is declared **on a model**, and the trigger objects in the
    database are named ``pgtrigger_<name>_<hash>``, not by the ``name``
    attribute alone. The legacy names (``registry_sync_metadatarecord_
    keywords_list`` and friends) are gone after ``0039``.
*   A trigger on a keywords **relation** sits on the unmanaged
    ``*KeywordsLink`` models of ``registry/models/metadata.py``. Django never
    puts the auto-created through model of a ``ManyToManyField`` into the
    migration state, and a trigger which the autodetector cannot see is a
    trigger without migrations -- the link models only make the existing
    relation tables addressable and never create, alter or drop them. New
    keyword relations which need a trigger declare it the same way; the
    operation ``AddKeywordsLinkTrigger`` exists because Django's migrate
    otherwise skips every operation for an unmanaged model.
*   The reverse of a trigger migration drops the trigger but leaves the
    ``pgtrigger_`` function behind (this is how the package removes triggers);
    a later forward migration or ``manage.py pgtrigger uninstall`` removes it.
    ``0039`` reverses to the legacy objects as ``0035`` left them -- their
    statements, reproduced verbatim in the migration with the widened empty
    array of #1075 -- so the rollback of the whole transfer is a supported
    path.


Why this was possible only now: pgviews and pgtrigger
=====================================================

The historic attempt (December 2023) is in git: the commit which added
``django-pgtrigger==4.11.0`` together with pgtrigger operations in the
squashed ``0001``, then churn migrations named
``remove_datasetmetadatarecordkeywords_sync_keywords_list_and_more``, and the
revert ``84509afc2`` which replaced the package with
``django-pgviews-redux==0.9.4``. The symptom recorded there -- triggers
disappearing from ``makemigrations`` -- is reproducible today, and its root
cause is *not* a package incompatibility:

``django-pgviews-redux`` ships its own ``makemigrations`` and ``migrate``
management commands whose ``autodetector`` is ``PGViewsAutodetector``.
``django-pgtrigger`` does not ship a command of its own; it patches
Django's *base* command classes with ``MigrationAutodetectorMixin``. Because
the app command shadows the patched base command, pgviews' autodetector wins
and pgtrigger's mixin never runs: seven triggers can be registered and
installed in the database while ``makemigrations --check`` reports no drift
and generates no trigger operations -- the triggers are silently invisible.
Django's ``commands.E001`` system check then forbids the obvious repair of
declaring both mixins on two commands: ``makemigrations`` and ``migrate`` must
share the *same* autodetector class.

The fix is a single project-level autodetector combining both mixins
(``backend/MrMap/migration_detection.py``:
``ViewsAndTriggersAutodetector(MigrationAutodetectorMixin,
PGViewsAutodetector)``) plus thin ``makemigrations``/``migrate`` command
wrappers in ``backend/MrMap/management/commands/`` which select it. App
commands are looked up in *reverse* ``INSTALLED_APPS`` order, so ``MrMap``,
which is listed before ``django_pgviews``, wins without reordering anything.

Materialized views are unaffected: ``ServiceAlertView`` remains a pgviews
``ReadOnlyView`` which is ``managed = False`` and created by the post-migrate
hook of ``system/apps.py``, and
``MATERIALIZED_VIEWS_DISABLE_SYNC_ON_MIGRATE`` stays on. No matview refresh
is reintroduced anywhere by this.


Writing a new trigger
=====================

Register it in an imported module (``registry/triggers.py`` is the pattern)::

    import pgtrigger
    from pgtrigger import Protect, Update, Delete

    @pgtrigger.register(Protect(name="append_only", operation=Update | Delete))
    class SomeModel(models.Model):
        ...

then ``makemigrations registry`` and ``migrate``. Prefer
``pgtrigger.Protect``, ``pgtrigger.Search`` or another contrib trigger before
writing raw plpgsql; where raw sql is unavoidable (as in the keyword rules,
which aggregate per row and fan out by name) keep the statements of the
trigger classes small and copy-test the value semantics in
``tests/django/registry/tests_keywords_list.py``.
