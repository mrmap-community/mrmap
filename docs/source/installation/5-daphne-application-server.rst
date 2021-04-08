.. _installation-5-application-server:

========
5. daphne
========

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
We need a `ini file for uwsgi <https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_uwsgi_ini>`_
and a `service definition for uwsgi <https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_uwsgi_service>`_

.. note::
    If you are using a virtualenv, you have to change the path to the uwsgi binary in `uwsgi service file <https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_uwsgi_service>`_
    to the one in the virtualenv eg. ``/opt/mrmap/venv/bin/uwsgi``
    If your installation directory differs from /opt/, you have to change it in the `ini file for uwsgi <https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_uwsgi_ini>`_


.. code-block:: console

    # copy uwsgi ini
    $ cp -a /opt/mrmap/install/confs/mrmap_uwsgi_ini /opt/mrmap/mrmap/MrMap/mrmap_uwsgi.ini
    # copy uwsgi systemd config (service file)
    $ cp -a /opt/mrmap/install/confs/mrmap_uwsgi_service /etc/systemd/system/uwsgi.service


2. Create directory for pid file according to mrmap_uwsgi.ini

.. code-block:: console

    $ mkdir /var/run/uwsgi
    $ chown www-data /var/run/uwsgi


3. Activate and start uwsgi service

.. code-block:: console

    $ systemctl enable uwsgi
    $ systemctl start uwsgi


Verify Service Status
*********************

1. Check the output of

.. code-block:: console

   $ systemctl status uwsgi

