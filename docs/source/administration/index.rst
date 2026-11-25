.. _administration:

Administration
==============

This section is the entry point for running a Mr.Map instance: what a released
version means, how a version reaches an instance and what an operator does
around that moment.

The operator runbook below is generated from the repository itself - the
workflows, the scripts and the policy documents each describe one verified step.
The release lifecycle itself is described in machine-readable form in
``scripts/release_lifecycle.json``; the contract suite
``scripts/test_release_lifecycle.py`` fails when the description and the tooling
drift apart, so what is written here is what the tooling actually does.

The three pages after the runbook are the access model and the outbound-fetch
policy: who reaches which resource through which interface, and which addresses
the backend may connect to when it is told to fetch a URL that somebody else
wrote. All three are built from Markdown now (#1597). Before that the build
loaded no Markdown parser at all, so they sat inside the documentation source
invisible to a reader while the code around them quoted them as the authority on
their own subject - ``backend/extras/ssrf.py`` names ``fetch-host-policy.md`` as
its policy document, and ``backend/accounts/views/auth.py`` points a reader at
``authentication.md`` from inside a docstring. They stay Markdown at the same
repository path, because that is the path the code quotes; the build reads them
where they are.

The low-memory runbook beside it follows the same convention for the
deployment-shape side of operations: its machine-readable form is
``scripts/low_memory_deployment.json``, held against the committed Compose
files and resolvers by ``scripts/test_low_memory_deployment.py``.

.. toctree::
   :maxdepth: 2

   release-operator-runbook
   authentication
   permissions
   fetch-host-policy
   low-memory-operator-runbook
