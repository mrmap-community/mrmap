.. _installation-5-application-server:

=========
5. daphne
=========

Installation
************

We use `daphne server <https://github.com/django/daphne>`_ for serving the application.

.. note::
    You can also split into serving normal http by use popular wsgi application servers such as `gunicorn <https://gunicorn.org>`_ or `uWSGI <https://uwsgi-docs.readthedocs.io/en/latest/>`_ .

1. If you use a virtualenv, activate it before installing daphne

.. code-block:: console

    $ source /opt/mrmap/venv/bin/activate
    (venv) $ python -m pip install daphne


Configure
*********

1. Adjust if needed and copy the config files to their destination:
We need a `service definition for daphne <https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_daphne_service>`_

.. code-block:: console

    # copy daphne systemd config (service file)
    $ cp -a /opt/mrmap/install/confs/mrmap_daphne_service /etc/systemd/system/daphne.service

3. Activate and start daphne service

.. code-block:: console

    $ systemctl enable daphne
    $ systemctl start daphne


Verify Service Status
*********************

1. Check the output of

.. code-block:: console

   $ systemctl status daphne

