.. _usage:


=====
Usage
=====


Metadata Catalouge
==================
Mr. Map provides a `csw <https://www.ogc.org/standard/cat/>`_ implementation to provide collected metadata.

The csw api is available under ``{schema}://{hostname}/csw``. The usage is described by the ogc specs and is not content of this documentation.

Collect Metadata
################

There are much ways Mr. Map collect metadata records which are described in this subsection.

1. Found by ogc service capabilities
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
If you register wms or wfs services, Mr. Map will find related metadata records inside the capabilities document and collect them inside background tasks.

2. harvested by other csw's
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Register other csw's as a service resource in Mr. Map. Mr. Map then will harvest them inside background tasks.


3. imported by file system
~~~~~~~~~~~~~~~~~~~~~~~~~~
You can also import metadata records by file system import.

First of all you need the container id of the backend container. Run the following command to list all running containers.

.. code-block:: console

    $ docker ps
    CONTAINER ID   IMAGE                           COMMAND                  CREATED        STATUS             PORTS                                             NAMES
    0dde49351793   mrmap_celery-worker             "/opt/mrmap/.bash_sc…"   18 hours ago   Up About an hour   8001/tcp, 0.0.0.0:3002->5678/tcp                  mrmap-celery-worker-1
    e383a3f0cba2   mrmap_backend                   "/opt/mrmap/.bash_sc…"   19 hours ago   Up About an hour   0.0.0.0:8001->8001/tcp, 0.0.0.0:3001->5678/tcp    backend-dev
    39b1d0412b62   mrmap_celery-beat               "/opt/mrmap/.bash_sc…"   19 hours ago   Up About an hour   8001/tcp                                          mrmap-celery-beat-1
    3ddfaa3a3646   postgis/postgis:15-3.3-alpine   "docker-entrypoint.s…"   20 hours ago   Up About an hour   0.0.0.0:5555->5432/tcp, :::5555->5432/tcp         mrmap-postgis-1
    cbe33a40f90d   redis:7.2.0-alpine              "docker-entrypoint.s…"   24 hours ago   Up About an hour   0.0.0.0:5556->6379/tcp, :::5556->6379/tcp         mrmap-redis-1
    27d72bcacffd   camptocamp/mapserver:7.6        "/docker-entrypoint …"   7 weeks ago    Up About an hour   8080/tcp, 0.0.0.0:8090->80/tcp, :::8090->80/tcp   mrmap-mapserver-1

Then you can simply run ``docker cp ./test.xml e383a3f0cba2:/var/mrmap/import`` or ``docker cp ./test.xml backend-dev:/var/mrmap/import`` to copy files to the container.

If the ``celery-beat`` and ``celery-worker`` container is running, the Mr. Map will find the new files automatically. Not importable files are renamed as ``ignore_{datestamp}_{oldfilename}`` and will be ignored by Mr. Map. 
In this case you need to study the logs to get more information why the file can't be imported by Mr. Map.

.. image:: ../images/sequence_diagram_file_import.svg
  :width: 100%
  :alt: Celery tasks livecycle