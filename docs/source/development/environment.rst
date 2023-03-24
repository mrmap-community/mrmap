.. _development-environment:


=====================
Environment Variables
=====================

We provide default environment files with the repository. All files starts with ``.env.{purpose}``


MrMap applications
##################

``MRMAP_USER``
**************

Used by setup command to create initial superuser.


``MRMAP_PASSWORD``
******************

Used by setup command while creating superuser to provide initial password.


``DJANGO_DEBUG``
*********************

Used to activate debugging features. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#debug>`__ for details.

.. warning::
    never use DJANGO_DEBUG=1 in pruction environment!


``DJANGO_SECRET_KEY``
*********************

Used to configure the secrete key which is used by django. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#secret-key>`__ for details.

.. warning::
    use a strong secret and never the default from the repository!

``DJANGO_ALLOWED_HOSTS``
************************

Used to configure the allowed hosts from the origin header. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#allowed-hosts>`__ for details.

``DJANGO_TIME_ZONE``
********************

Used to configure the timezone which shall be used in MrMap. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#time-zone>`__ for details.

``SQL_ENGINE``
**************

Used to configure the sql engine which is used. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#engine>`__ for details.


``SQL_DATABASE``
****************

Used to configure the name of the schema. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#name>`__ for details.


``SQL_USER``
************

Used to configure the name of the user which shall be used to connect to the database. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#user>`__ for details.


``SQL_PASSWORD``
****************

Used to configure the password of the user which shall be used to connect to the database. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#password>`__ for details.


``SQL_HOST``
************

Used to configure the ip/dns name of the database host. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#host>`__ for details.


``SQL_PORT``
************

Used to configure the port of the database host. See `django docs <https://docs.djangoproject.com/en/3.2/ref/settings/#port>`__ for details.


``REDIS_HOST``
**************

Used to configure the ip/dns name of the redis host.


``REDIS_PORT``
**************

Used to configure the port of the redis host.


``MAPSERVER_URL``
*****************

Used to configure the url of the mapservice instance.

``MAPSERVER_SECURITY_MASK_FILE_PATH``
*************************************

Used to configure the map file for security proxy. This file needed to be installed on the used mapserver which is configured by ``MAPSERVER_URL``.