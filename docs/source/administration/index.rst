.. _administration:

Administration
==============

This section is the entry point for running a MrMap instance: what a released
version means, how a version reaches an instance and what an operator does
around that moment.

The operator runbook below is generated from the repository itself - the
workflows, the scripts and the policy documents each describe one verified
step. The release lifecycle itself is described in machine-readable form in
``scripts/release_lifecycle.json``; the contract suite
``scripts/test_release_lifecycle.py`` fails when the description and the
tooling drift apart, so what is written here is what the tooling actually
does.

.. toctree::
   :maxdepth: 2

   release-operator-runbook

Authentication and permissions
------------------------------

The access model - who sees which resource through which interface - is
described in two companion documents that predate this section's restructure:
``docs/source/administration/authentication.md`` and
``docs/source/administration/permissions.md`` in the repository. They are
plain Markdown and the portal does not render Markdown yet, so read them from
the repository; folding them into this section belongs to the documentation
portal work (#1597).

Which hosts the instance may fetch
---------------------------------

``docs/source/administration/fetch-host-policy.md`` in the repository is the operator
description of the third control point: which addresses the backend may connect to when it
fetches a URL that somebody else wrote -- the service URL of a registration, the links an
upstream capabilities document advertises, the metadata reference of a harvest and every
redirect target along the way. It states the default, the two deployment variables which
narrow or widen it, and the worked examples for an internal catalogue and a cloud host.
Like the two documents above it is plain Markdown, so read it from the repository.
