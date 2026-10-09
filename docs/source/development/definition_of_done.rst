.. _development-dod:


========================
Definition of Done (DoD)
========================

Run the following checks before starting a pullrequest to avoid of error while github actions.


.. |check| raw:: html

    <input checked=""  type="checkbox">

.. |check_| raw:: html

    <input checked=""  disabled="" type="checkbox">

.. |uncheck| raw:: html

    <input type="checkbox">

.. |uncheck_| raw:: html

    <input disabled="" type="checkbox">


|uncheck| run ``flake8`` on the changed files. ``backend/setup.cfg`` mirrors the settings CI uses, so
  ``flake8 <path>`` from ``backend/`` reports the same findings as the ``pre-commit-check`` job.

|uncheck| run the targeted Django tests of the touched app in Docker; run the full unit suite when
  the change is risky or touches shared code (see ``backend/AGENTS.md`` for commands and timings,
  ``backend/tests/AGENTS.md`` for test conventions)

|uncheck| run ``npm run type-check`` and the specs of the touched components
  (``npm run test -- --run src/components/Resource/<Resource>``). Both have an open red baseline on
  ``main``; compare against the counts in ``frontend/AGENTS.md`` instead of expecting a green run,
  and do not add new failures or spec files that are named ``.spec.ts`` / ``.spec.tsx``

|uncheck| run :ref:`makemigrations <running_management_commands_makemigrations>`

|uncheck| run :ref:`migrate <running_management_commands_migrate>`

|uncheck| run :ref:`makemessages <running_management_commands_makemessages>`

|uncheck| check translations in backend/locale/de/LC_MESSAGES/django.po (empty strings are not allowed)

|uncheck| run :ref:`compilemessages <running_management_commands_compilemessages>`

|uncheck| run :ref:`tests <running_management_commands_tests>`

|uncheck| run the Behave scenarios covering the changed API or workflow

|uncheck| run production compose file ``docker compose -f docker-compose.yml up --build``