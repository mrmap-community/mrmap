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


|uncheck| run :ref:`makemigrations <running_management_commands_makemigrations>`

|uncheck| run :ref:`migrate <running_management_commands_migrate>`

|uncheck| run :ref:`makemessages <running_management_commands_makemessages>`

|uncheck| check translations in mrmap/locale/de/LC_MESSAGES/django.po (empty strings are not allowed)

|uncheck| run :ref:`compilemessages <running_management_commands_compilemessages>`

|uncheck| run :ref:`tests <running_management_commands_tests>`

|uncheck| run production compose file ``docker-compose -f docker-compose.yml up --build``