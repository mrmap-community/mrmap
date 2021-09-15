.. _development-pycharm-cfg:


=====================
Pycharm configuration
=====================

.. warning::
    Debugging dockerized projects in pycharm needs a pycharm professional version.

Configuration of Pycharm and Docker
************************************

Configure docker in pycharm:

* Open Pycharm and point it to the root directory of mrmap, eg. `/opt/mrmap/`
* Goto File->Settings->Plugins and search for docker to install it.
* Goto File->Settings->Build,Execution,Development->Docker
* Click on the plus sign to add a docker configuation.
* Use the default settings and click on apply, it should say "Connection successful".

.. image:: ../images/docker_pycharm_settings.png
  :width: 800
  :alt: docker pycharm settings

Next we have to mark the mrmap folder as source folder.

* Right click on the mrmap folder in the pycharm directory tree, eg. /opt/mrmap/mrap
  and select "Mark Directory as -> Source Folder"

Runconfigurations
*****************
We provide a set of default run configurations for pycharm. Pycharm should find that configurations automatically. See example image below.

.. image:: ../images/pycharm_run_cfg_example.png
  :width: 800
  :alt: docker pycharm settings
