.. _installation-6-http-server:

========
6. Nginx
========

Install
*******

For hosting our web application we will use `the most popular web server on the internet <https://news.netcraft.com/archives/category/web-server-survey/>`_: the `Nginx <https://nginx.org>`_ webserver.

Debian
======

.. code-block:: console

   $ apt install -y nginx fcgiwrap


Configure
*********

We confiure our webserver to serve SSL traffic, if you dont want to encrypt your data there
is another configuration file for plain HTTP in the conf folder.

1. Create a certificate:

.. code-block:: console

    $ openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/nginx-selfsigned.key -out /etc/ssl/certs/nginx-selfsigned.crt


2. Copy Nginx config file to its place and enable it by creating a symlink. Delete the default conf.

.. note::
    If youre not installing to ``/opt/`` you have to change the folder of the ``/static`` route in the `nginx conf <https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_nginx_ssl>`_.
    

.. code-block:: console

    $ cp -a /opt/mrmap/install/confs/mrmap_nginx_ssl /etc/nginx/sites-available/mrmap
    $ rm /etc/nginx/sites-enabled/default
    $ ln -s /etc/nginx/sites-available/mrmap /etc/nginx/sites-enabled/mrmap


3. Change server_name to your name or ipaddress in `/etc/nginx/sites-available/mrmap`. In the following example the server is available under `10.0.10.10`

.. code-block:: console

    server {
        listen 80;
        server_name 10.0.10.10;
        ...
    }
    server {
        listen 443 ssl;
        server_name 10.0.10.10;
        ...
    }



4. Change ``HTTP_OR_SSL`` setting to ``https://`` in ``settings.py``

.. code-block:: console

    $ vim /opt/mrmap/mrmap/MrMap/settings.py


Verify Service Status
*********************

1. Restart webserver and test

.. code-block:: console

   $ systemctl restart nginx


2. You should see the login page after opening ``http://YOUR-IP-ADDRESS``

.. image:: ../images/mrmap_loginpage.png
  :width: 800
  :alt: MrMap login page
