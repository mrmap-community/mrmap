.. _development-commands:


========
Commands
========

We added some custom commands to simplify our development processing.

dev_messages
############

This command executes the default built-in `django makemessages <https://docs.djangoproject.com/en/3.2/ref/django-admin/#makemessages>`_ command for all configured languages.
After that a check script will proof for empty translation strings. IF empty translations are founded, it will exit with failure.

.. note::
    This command will run on any pull-request for the master branch. With that we make sure that the master branch contains all needed translations.


To run call:

.. code-block:: shell

    python manage.py dev_messages