..
   Portal landing page (#1597, epic #1589).

   One Sphinx build, one theme, one navigation tree - the five sections the
   issue names (user, administration, developer, API reference, release notes)
   over the corpus that already exists. The section *paths* are unchanged from
   before this issue on purpose: `usage/index.html`, `installation/index.html`,
   `development/index.html` and the rest keep the URLs they had, because links
   from the README, from issues and from deployed instances point at them, and a
   modernised portal that breaks those links has not been modernised, it has been
   reset. What changed is the grouping: the toctrees below are ordered and
   captioned by the audience ADR-0001 section 3 derives from the roles Mr.Map
   already enforces, so a reader arrives through their job rather than through
   the history of the directory layout. A page belongs to one section: the
   autodoc indexes hang off ``api/index``, the page that explains why their
   content depends on the build, rather than appearing beside it.

   An audience gets a section only where the software has a role to anchor it.
   Cataloguer, administrator, integrator, developer and operator are the
   permission classes and endpoint groups in the code, not names invented for the
   docs - which is why this list cannot drift away from the product.

================
Welcome to MrMap
================

.. image:: images/mr_map.png
  :width: 200
  :alt: MrMap logo

Mr.Map is a geoservice registry and metadata catalogue: it registers OGC
services, collects and curates their metadata, and serves both to clients and to
other catalogues.

This portal documents one version of the software. The version in the sidebar is
the version this build documents, taken from the canonical ``VERSION`` file of
the release it was built from; :doc:`release_notes/index` lists what each version
changed. The version selector in the theme lists the released tags that have
their own build.

Pick the section that matches what you are doing:

.. toctree::
   :maxdepth: 4
   :caption: User - cataloguing services and records

   introduction/index
   usage/index

.. toctree::
   :maxdepth: 4
   :caption: Administrator and operator - running an instance

   installation/index
   administration/index

.. toctree::
   :maxdepth: 4
   :caption: API reference - the interfaces an integrator codes against

   api/index

.. toctree::
   :maxdepth: 4
   :caption: Developer - how it is built and why

   system_architecture/index
   development/index
   design/index

.. toctree::
   :maxdepth: 2
   :caption: Release notes

   release_notes/index

.. toctree::
   :hidden:
   :maxdepth: 2

   genindex
