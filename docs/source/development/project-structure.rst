.. _development-project-structure:


=================
Project Structure
=================

Preamble
========

In django universe the official propagated way to strucure a project is to use `apps` (a carryover from Django vernacular). 
But there are many discussions out there about the question `when we have to make an app?`.

To understand our project structure, it is important to specify some terms first, so that everyone which likes to understand the code uses the same vocabulary.


.. _what_is_an_app:

What is an app?
---------------

In our opinion an app in a django project shall be a django specific python package, which is independend from other apps. 
The most common reason to start an app is to create reusable code.


A Django View is Not a Controller
---------------------------------

A default app structure in django is splitted in some basic modules:

* ``app_folder``
  * ``models.py``
  * ``urls.py``
  * ``views.py``
  * ``...``

Like discussed in `article <https://masteringdjango.com/django-tutorials/mastering-django-structure/>`_ the module ``views.py`` is **not** the controller module. 
Citation from the article: "The view in Django is most often described as being equivalent to the controller in MVC, but it’s not—it’s still the view."

Where to put app logic code then?
---------------------------------

Follow the question from the `article <https://masteringdjango.com/django-tutorials/mastering-django-structure/>`_::

    Does the function/class return a response?

        * YES — it’s a view. Put it in the views module (views.py).
        * NO — it’s not a view, it’s app logic. Put it somewhere else (somewhere_else.py).


Package Overview
================

* ``accounts``: generic implementation of access control list management for django guaridan permissions.
* ``axis_order_cache``: django cache implementation for axis ordering from remote epsg api.
* ``extras``: global project wide used django specific code.
* ``MrMap``: django project root for mrmap project.
* ``notify``: handles notifications over websockets.
* ``ows_lib``: library which has an ogc client for wms, wfs and csw services and the needed xml mappers.
* ``registry``: spatial service registry to register and manage services like wms, wfs, csw. (monolith app)
* ``tests``: django and behave tests.

package/app structure
---------------------

As described in :ref:`Preamble <what_is_an_app>` on the first hirachy level we only have `independend` packages.

In django specific packages which are small, we use the common django way to split modules:

* ``app_folder/``
  
  * ``models.py``
  * ``urls.py``
  * ``views.py``
  * ``...``


In larger apps we use the following structure:

* ``app_folder/`` 
  
  * ``models/``
  
    * ``ogc_service.py``
    * ``metadata.py``
  
  * ``views/``
  
    * ``ogc_service.py``
    * ``metadata.py``
  
  * ``...``

FAQ
===

Why is the registry app a monolith?
-----------------------------------

Like described in :ref:`Preamble <what_is_an_app>` we are of the opinion that a django app shall be independend from others to reuse them. 
If we would split the registry app into different pieces like ``monitoring``, ``security``, ``...`` we will not can use these outsourced apps stand alone.
So it makes no sens to split them into different `apps`. 