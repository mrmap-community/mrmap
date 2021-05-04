.. _installation:


============
Installation
============

The installation instructions provided here have been tested to work on Debian 10. The particular commands needed to install dependencies on other distributions may vary significantly. Unfortunately, this is outside the control of the MrMap maintainers. Please consult your distribution's documentation for assistance with any errors.
Take a look at the `instructions <https://github.com/mrmap-community/mrmap/tree/master/install>`_ in the install folder on how to deploy the project on a production system.

The following sections detail how to set up a new instance of MrMap:

#. :ref:`PostgreSQL database <installation-1-postgresql>`
#. :ref:`Redis <installation-2-redis>`
#. :ref:`Mapserver <installation-3-mapserver>`
#. :ref:`MrMap components <installation-4-mrmap>`
#. :ref:`Application server <installation-5-application-server>`
#. :ref:`HTTP Server <installation-6-http-server>`


**Application stack**

Below is a simplified overview of the MrMap application stack for reference:

.. image:: ../images/app_stack.png
  :width: 800
  :alt: MrMap application stack

.. toctree::
   :hidden:
   :maxdepth: 3

   0-requirements
   1-postgresql
   2-redis
   3-mapserver
   4-mrmap
   5-application-server
   6-http-server
