.. _installation-5-application-server:

=====================
5. Application server
=====================

wsgi application server
#######################

We use `gunicorn server <https://github.com/benoitc/gunicorn>`_ for serving the wsgi application.

.. note::
    You can also use other wsgi application servers such as `uWSGI <https://uwsgi-docs.readthedocs.io/en/latest/>`_ .

1. If you use a virtualenv, activate it before installing gunicorn

.. code-block:: console

    $ source /opt/mrmap/venv/bin/activate
    (venv) $ python -m pip install gunicorn


Configure
*********

1. Adjust if needed and copy the config files to their destination:
We need a `service definition for gunicorn <https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_gunicorn_service>`_

.. code-block:: console

    # copy daphne systemd config (service file)
    $ cp -a /opt/mrmap/install/confs/mrmap_gunicorn_service /etc/systemd/system/gunicorn.service

3. Activate and start gunicorn service

.. code-block:: console

    $ systemctl enable gunicorn
    $ systemctl start gunicorn


Verify Service Status
*********************

1. Check the output of

.. code-block:: console

   $ systemctl status gunicorn


asgi application server
#######################

We use `uvicorn server <https://github.com/encode/uvicorn>`_ for serving the asgi application.

.. note::
    You can also use other asgi application servers such as `daphne <https://github.com/django/daphne>`_ .

1. If you use a virtualenv, activate it before installing gunicorn

.. code-block:: console

    $ source /opt/mrmap/venv/bin/activate
    (venv) $ python -m pip install uvicorn
    (venv) $ python -m pip install websockets


Configure
*********

1. Adjust if needed and copy the config files to their destination:
We need a `service definition for uvicorn <https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_uvicorn_service>`_

.. code-block:: console

    # copy daphne systemd config (service file)
    $ cp -a /opt/mrmap/install/confs/mrmap_uvicorn_service /etc/systemd/system/uvicorn.service

3. Activate and start uvicorn service

.. code-block:: console

    $ systemctl enable uvicorn
    $ systemctl start uvicorn


Verify Service Status
*********************

1. Check the output of

.. code-block:: console

   $ systemctl status uvicorn

