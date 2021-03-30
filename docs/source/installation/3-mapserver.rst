.. _installation-3-mapserver:

============
3. Mapserver
============

Installation
************

`Mapserver <https://mapserver.org/>`_ is an Open Source platform for publishing spatial data and interactive mapping applications to the web.


Debian
======

.. code-block::

   apt install -y cgi-mapserver


Configure
*********

Configuration of mapserver will be handled in :ref:`the webserver setup <installation-6-http-server>`.

Verify Service Status
*********************

1. Use the ``mapserv`` utility to ensure the Mapserver service is functional:

.. code-block::

   $ mapserv -v
   MapServer version 7.2.2 OUTPUT=PNG OUTPUT=JPEG OUTPUT=KML SUPPORTS=PROJ SUPPORTS=AGG SUPPORTS=FREETYPE SUPPORTS=CAIRO SUPPORTS=SVG_SYMBOLS SUPPORTS=RSVG SUPPORTS=ICONV SUPPORTS=FRIBIDI SUPPORTS=WMS_SERVER SUPPORTS=WMS_CLIENT SUPPORTS=WFS_SERVER SUPPORTS=WFS_CLIENT SUPPORTS=WCS_SERVER SUPPORTS=SOS_SERVER SUPPORTS=FASTCGI SUPPORTS=THREADS SUPPORTS=GEOS SUPPORTS=PBF INPUT=JPEG INPUT=POSTGIS INPUT=OGR INPUT=GDAL INPUT=SHAPEFILE

