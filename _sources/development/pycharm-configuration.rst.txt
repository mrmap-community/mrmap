.. _development-getting-started:


=====================
Pycharm configuration
=====================


Install needed software
************************************

 
**Pycharm**:

For the installation of Pycharm please use the official documentation.

https://www.jetbrains.com/pycharm/

**Docker**:

You need at least:

* docker > 19
* docker-compose > 1.20

Docker setup is described in:

`docker setup <https://mrmap-community.github.io/mrmap/development/docker.html>`_


Configuration of Pycharm and Docker
************************************

If not already done, add the user, which is starting pycharm to the docker group

```
sudo usermod -aG docker <your-user>
```

Configure docker in pycharm:

* Open Pycharm and point it to the root directory of mrmap, eg. /opt/mrmap/
* Goto File->Settings->Plugins and search for docker to install it.
* Goto File->Settings->Build,Execution,Development->Docker
* Click on the plus sign to add a docker configuation.
* Use the default settings and click on apply, it should say "Connection successful".

.. image:: ../images/docker_pycharm_settings.png
  :width: 800
  :alt: docker pycharm settings

Next we have to mark the mrmap folder as source folder and
create service configurations for the project.

* Right click on the mrmap folder in the pycharm directory tree, eg. /opt/mrmap/mrap
  and select "Mark Directory as -> Source Folder"

* On the upper right of the pycharm interface you should see a button with "Add configuration".

.. image:: ../images/add_pycharm_configuration.png
  :width: 800
  :alt: add pycharm settings

* Create a docker configuration in Pycharm.

.. image:: ../images/docker_pycharm_configuration.png
  :width: 800
  :alt: add pycharm settings

* Create a runserver configuration in Pycharm.

.. image:: ../images/runserver_pycharm_configuration.png
  :width: 800
  :alt: runserver pycharm settings


* Create a celery configuration in Pycharm.

.. image:: ../images/celery_pycharm_configuration.png
  :width: 800
  :alt: celery pycharm settings

* Create a compound configuration in Pycharm to bundle all the services.

.. image:: ../images/compound_pycharm_configuration.png
  :width: 800
  :alt: compound pycharm configuration
