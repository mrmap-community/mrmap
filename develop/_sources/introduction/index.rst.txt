.. _introduction:

============
Introduction
============

.. image:: ../images/mr_map.png
  :width: 200
  :alt: MrMap logo

What is MrMap?
**************

Mr. Map is a generic registry for geospatial data, metadata, services and their describing documents (e.g. web map services `WMS <https://www.opengeospatial.org/standards/wms>`_, web feature services `WFS <https://www.opengeospatial.org/standards/wfs>`_ and all the other `OGC <http://www.opengeospatial.org/>`_ stuff. A similar project maybe `Hypermap-Registry <http://cga-harvard.github.io/Hypermap-Registry/>`_ - but it lacks off many things which are needed in practice. The information model was inspired by the old well known `mapbender2 <https://git.osgeo.org/gitea/GDI-RP/Mapbender2.8>`_ project and somewhen will be replaced by mrmap.

Since most GIS solutions out there are specified on a specific use case or aged without proper support, the need for an free and open source, generic geospatial registry system is high.

It encompasses the following aspects:

* User management
* Organisation registry
* Service management (wms/wfs/csw)
* Metadata Editor (service/dataset)
* Metadata views
* ETF testing framework interface (service/dataset)
* Monitoring of registrated services (wms/wfs)
* Proxy (service/dataset metadata)
* Secured Access (wms/wfs/layer/featuretype)
* Publisher system (orgs/groups/users)
* Dashboard
* Catalogue and APIs (REST interfaces for the resources)
* CSW interface

What MrMap Is Not
*****************

While MrMap strives to cover many areas of geodata infrastructure, the scope of its feature set is necessarily limited. This ensures that development focuses on core functionality and that scope creep is reasonably contained. To that end, it might help to provide some examples of functionality that MrMap does not provide:

* Enhanced web-based Map viewer component


Design Philosophy
*****************

MrMap was designed with the following tenets foremost in mind.

Keep it Simple
**************

When given a choice between a relatively simple `80% solution <https://en.wikipedia.org/wiki/Pareto_principle>`_ and a much more complex complete solution, the former will typically be favored. This ensures a lean codebase with a low learning curve.


Application Stack
*****************

NetBox is built on the `Django <https://djangoproject.com/>`_ Python framework and utilizes a `PostgreSQL <https://www.postgresql.org/>`_ database. It runs as a ASGI service behind your choice of HTTP server.

.. list-table::
   :widths: 50 50
   :header-rows: 1

   * - Function
     - Component
   * - HTTP service
     - nginx
   * - Application
     - Django/Python
   * - Database
     - PostgreSQL 11.10+
   * - Task queuing
     - Redis/django-rq

Supported Python Versions
*************************

MrMap supports Python3.7 environment currently.

Getting Started
***************

See the :ref:`installation guide <installation>` for help getting MrMap up and running quickly.

