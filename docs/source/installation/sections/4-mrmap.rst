.. _installation-4-mrmap:

=====================
4. MrMap Installation
=====================

This section of the documentation discusses installing and configuring the MrMap application itself.
You can either setup a virtualenv for python or use system python if it is above Python3.7.
If you want to use system python just skip the step to create and activate a virtualenv.

Install System Packages
***********************

Begin by installing all system packages required by MrMap and its dependencies.

.. note::
    MrMap requires Python 3.7, or 3.8.

Debian
======

On debian 10 you have python3.7 available in the system packages, on other versions or distros you might have to compile it yourself.

.. code-block::

   apt install -y libcurl4-openssl-dev libssl-dev python3.8-dev gdal-bin virtualenv git gcc libpq-dev


Initial setup Mr. Map
*********************

1. Clone the project from the repo to your preferred install directory, we use ``/opt/`` in this example:

.. code-block::

   cd /opt/
   git clone https://github.com/mrmap-community/mrmap


2. Create your virtualenv and activate it (skip this step if you want to use system python):

.. code-block::

   virtualenv -ppython3.7 /opt/mrmap/venv
   source /opt/mrmap/venv/bin/activate


3. Install all requirements in to the virtualenv, make sure to use python3.7 binary if you are not using a virtualenv:

.. code-block::

   (venv) $ python -m pip install -r /opt/mrmap/mrmap/requirements.txt


4. Set database parameters in /opt/mrmap/mrmap/MrMap/sub_settings/db_settings.py

.. code-block::

   ...
   'NAME': 'mrmap',
   'USER': 'mrmap',
   'PASSWORD': 'J5brHrAXFLQSif0K',
   ...


5. Run django migrations:
.. code-block::

   (venv) $ python /opt/mrmap/mrmap/manage.py migrate

6. (Optional) Configure proxy:

Make sure the ``HTTP_PROXY`` variable in ``MrMap/settings.py`` is set correctly for your system.

7. Run setup routine to get initialized db with admin user for mr. map:

.. code-block::

   (venv) $ python /opt/mrmap/mrmap/manage.py setup

8. Change Hostname in case you are not localhost

.. code-block::

   change hostname in /opt/mrmap/mrmap/MrMap/sub_settings/dev_settings.py



Test if everything works
************************

.. note::
    You can run the following commands in background by adding a trailing &

1. Start up celery process (celery will do async jobs for us)

        (venv) $ cd  /opt/mrmap/mrmap/
        (venv) $ celery -A MrMap worker -l INFO

2. Start up celery beat process

        (venv) $ celery -A MrMap beat -l INFO

3. Collect Static files and start up mr. map

        (venv) $ python manage.py collectstatic
        (venv) $ python manage.py runserver_plus 0.0.0.0:8000

.. note::
    At this point you have a full working instance of MrMap running. This is sufficient if your intention is development.
    In the next sections we setup system services for all the needed commands.
    `Runserver_plus <https://django-extensions.readthedocs.io/en/latest/runserver_plus.html>`_ gives us more debug informations.



4. You should see the login page after opening http://127.0.0.1:8000 or http://YOUR-IP-ADDRESS:8000:

.. image:: ../../images/mrmap_loginpage.png
  :width: 800
  :alt: MrMap login page

You can now login with the user you configured in your python manage.py setup routine.

Setup system services for celery and celery beat
************************************************

We dont want to start celery and celery beat manually.  
To automate this process we setup system services with systemd.

1. Create directory for pid file and logs

.. code-block::

    mkdir /var/run/celery
    mkdir /var/log/celery
    chown www-data /var/run/celery
    chown www-data /var/log/celery
    chown -R www-data /opt/mrmap/mrmap/logs/


2. Adjust if needed and copy the config files to their destination:
We need a `environment file for celery <https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_celery_environment>`_
and a `service definition for celery <https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_celery_service>`_.

.. note::
     If you are using a virtualenv you have to adjust celery path in the environment file.  
     If your installation directory differs from /opt/ you have to change the working directory in the service definition of celery.

.. code-block::

    # copy celery environment file
    cp -a /opt/mrmap/install/confs/mrmap_celery_environment /etc/default/celery
    # copy celery service file
    cp -a /opt/mrmap/install/confs/mrmap_celery_service /etc/systemd/system/celery.service


3. Activate and start celery service

.. code-block::

    systemctl enable celery
    systemctl start celery


4. Check if its running

.. code-block::

    systemctl status celery

