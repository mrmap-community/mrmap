.. _development-pycharm-cfg:


=====================
Pycharm configuration
=====================

.. warning::
    Debugging dockerized projects in pycharm needs a pycharm professional version.

1. Configuration of Pycharm and Docker
**************************************

* Open Pycharm and point it to the root directory of mrmap, eg. `/opt/mrmap/`
* Goto File->Settings->Plugins and search for docker to install it.
* Goto File->Settings->Build,Execution,Development->Docker
* Click on the plus sign to add a docker configuation.
* Use the default settings and click on apply, it should say "Connection successful".

.. image:: ../images/development/pycharm/docker_pycharm_settings.png
  :width: 100%
  :alt: docker pycharm settings

2. Configure project structure
******************************

Next we have to mark the mrmap folder as source folder.

* Right click on the mrmap folder in the pycharm directory tree, eg. /opt/mrmap/mrap
  and select "Mark Directory as -> Source Folder"

3. Add remote interpreter
*************************

Add one remote interpreter per container you want to debug. 

.. image:: ../images/development/pycharm/create_remote_interpreter.png
  :width: 100%
  :alt: create remote interpreter


4. Runconfigurations
********************

We provide a set of default run configurations for pycharm. Pycharm should find that configurations automatically. See example image below.

.. image:: ../images/development/pycharm/pycharm_run_cfg_example.png
  :width: 100%
  :alt: docker pycharm settings

Finally you have to change the remote interpreter to the specific remote interpreter of the docker service which the command runs in to. For example add the remote interpreter for service ``gunicorn`` to the run configuration ``Docker-Compose: mrmap debug gunicorn``.

Example
*******
See full example of how to start debugging below.

.. image:: ../images/development/pycharm/full_example.gif
  :width: 100%
  :alt: full example of debugging with pycharm