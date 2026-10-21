.. _development-vscode-cfg:


================================
Visual Studio Code configuration
================================

All necessary run configurations to starting development are provided with the repository. 
The configuration file is located under ``{local-path-to-repo}/.vscode/tasks.json``.

1. Open repo in vscode
======================

Go to ``File -> Open Folder...`` and select the root folder of the downloaded repo.

2. Start container in debugging mode
====================================

Currently there are three containers which executes MrMap application logic. For all of those containers one run configuration is provided.

Use the vscode shortcut ``ctrl + shift + p`` to use the `Command Palette`.
Start typing ``tasks: r``. QuickOpen will show you possible results for your search. Select ``Tasks: Run Task`` and smash the enter button. In second autoselect listing you can now choice one of our pre configured run configurations.

.. figure:: ../images/development/vscode/start_task.gif
  :width: 100%
  :alt: Starting a task

  Starting a task


For example you choose ``Docker Compose: mrmap debug gunicorn`` and smash the the enter button again, vscode will open a new terminal for you, where the docker container is running.

.. figure:: ../images/development/vscode/gunicorn_container_run_example.gif
  :width: 100%
  :alt: Gunicorn container run example

  Gunicorn container run example


3. Connect with debugger to the container
=========================================

The container will show you at least ``waiting for debugging client``. Now you have to connect to the container with the integrated debugger of vscode. Again there are ready to use run configurations located under ``{local-path-to-repo}/.vscode/launch.json``.

Again you can start debugger by using the `Command Palette`. So use shortcut ``ctrl + shift + p`` again and start typing ``>debug: sel``


.. figure:: ../images/development/vscode/gunicorn_container_debugger_connect.gif
  :width: 100%
  :alt: Gunicorn container debugger connect example

  Gunicorn container debugger connect example
    
Visual studio code will now attach to the remote container. You will see that the container finaly start gunicorn service.

.. figure:: ../images/development/vscode/gunicorn_container_debugger_connect_done.gif
  :width: 100%
  :alt: Gunicorn container debugger connect successfully example

  Gunicorn container debugger connect successfully example

Now you are able to debug code in vscode. See full example video below.

.. figure:: ../images/development/vscode/full_example.gif
  :width: 100%
  :alt: Full example of starting container and connect with debugger

  Full example of starting container and connect with debugger


4. Automatic linting and formatting
==================================

Install the workspace recommendations from ``.vscode/extensions.json``: Python, Pylance,
Flake8, autopep8 and ESLint. Select the project's ``.venv`` with ``Python: Select Interpreter``.
Python formatting runs on save; Flake8 uses ``backend/setup.cfg`` and the tools installed in
that environment. Python linting does not require loading Django or host GDAL.

ESLint reports frontend findings while typing and fixes supported findings on explicit save.
It uses ``frontend/eslint.config.mjs``. The separate TypeScript import organizer is not enabled,
so Perfectionist owns import ordering. Some lint findings require a manual correction.

Editor ESLint needs Node and the project dependencies in the environment where its extension
runs. In a Docker-only environment, attach VS Code to the frontend container and open
``/opt/mrmap/frontend`` there; do not install Node or dependencies into the host checkout.
The ``Frontend: run lint``, ``Frontend: run type check``, ``Frontend: run test`` and
``Frontend: run test with coverage`` tasks always use the dedicated Compose test service.
Initialize its dependency volume with the command in :ref:`development-code-quality` first.

See :ref:`development-code-quality` for CI gates, coverage reports and static security analysis.
