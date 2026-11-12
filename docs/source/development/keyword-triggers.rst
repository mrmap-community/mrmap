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
module). The three record types share trigger classes; table and foreign-key
names come from their Django model metadata. To change a rule, edit its class
there and run::

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
*   A trigger on a keywords **relation** sits on the explicit, managed
    ``*KeywordsLink`` through models of ``registry/models/metadata.py``.
    Each record's ``keywords`` field names its through model; that model owns
    the existing relation table, including the unique record/keyword pair,
    and uses ordinary ``pgtrigger.migrations.AddTrigger`` operations.
    The conversion preserves the existing table names, columns, relations and
    triggers through the state-only migration
    ``0046_explicit_keyword_through_models``. Other metadata types retain
    their automatic keywords relations. Migration ``0039`` originally used
    unmanaged mappings to expose these tables to the autodetector, which
    cannot track automatic through models. ``AddKeywordsLinkTrigger`` remains
    available solely for applying and reversing that historical migration.
*   The reverse of a trigger migration drops the trigger but leaves the
    ``pgtrigger_`` function behind (this is how the package removes triggers);
    a later forward migration or ``manage.py pgtrigger uninstall`` removes it.
    ``0039`` reverses to the legacy objects as ``0035`` left them -- their
    statements, reproduced verbatim in the migration with the widened empty
    array of #1075 -- so the rollback of the whole transfer is a supported
    path.


Migration compatibility
=======================

``django-pgtrigger`` patches Django's standard ``makemigrations`` and
``migrate`` commands. Its migration integration is enabled by default.
No project-specific commands or combined autodetector are needed now that
``django_pgviews`` is no longer an installed app.

The earlier workaround in commit ``7db0a0ebc`` combined pgviews' autodetector
with pgtrigger's because pgviews' commands shadowed Django's patched commands.
The consumers of pgviews have all been retired: ``e05e171d3`` removed the
searchable projections, ``1711ab1ec`` removed the statistics materialized views,
and ``1b1db1855`` replaced the final alerts view with stored rows. The combined
autodetector, command wrappers, missing-view startup hook and view settings
are therefore obsolete.

Keep ``django-pgviews-redux`` as a dependency until a first-release
migration reset: historical registry migrations still import its view
operations. Those migrations carry the SQL needed to restore the old views
on rollback, independently of an installed pgviews app or startup hook.
Likewise, the old keyword SQL and ``AddKeywordsLinkTrigger`` remain necessary
for applying and reversing the existing migration chain.

The live tests check installation through pgtrigger's status API and retain
the keyword value, fixture, history and long-keyword regressions. Historical
object replacement and rollback are tested in
``tests/django/registry/models/tests_keyword_migrations.py``.


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
