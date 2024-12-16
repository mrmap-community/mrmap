.. _development-getting-started:


===============
Getting Started
===============

.. warning::
    **pre-condition**: run :ref:`installation guide <installation>` first before you start working on this section.

Cause MrMap is full dockerized, the development of it is priciple possible on any operating system. Feel free to use the development ide of your choice.

We provide configuration files for `vscode <https://code.visualstudio.com/>`_. 

* To configure vscode see :ref:`documentation <development-vscode-cfg>`


.. note::
    Cause everthing is running with docker, all management commands need to be called inside the corresponding container.
    See :ref:`Running Management Commands <running_management_commands>`

 
Branch structure
================

The MrMap project utilizes three persistent git branches to track work:

* ``master`` - Serves as a snapshot of the current stable release
* ``feature`` - Tracks work on an upcoming new feature
* ``bug`` - Tracks work on an bugfix


Typically, you'll base pull requests off of the ``master`` branch.

.. _running_management_commands:

Running management commands
===========================


.. note::
    As pre condition MrMap application must be running.

    .. code-block:: console

        $ docker compose -f ./docker-compose.yml up --build


.. note::
    The prefix of started docker container name is always the name of the root folder where the docker-compose file lives in. In examples below, my root folder name is ``mrmap``.


Running echo
************

.. code-block:: console

    $ docker exec -it mrmap_gunicorn_1 echo "I'm inside the container!"

.. _running_management_commands_makemigrations:

Running makemigrations
**********************

.. code-block:: console

    $ docker exec -it mrmap_gunicorn_1 python /opt/mrmap/manage.py makemigrations

.. _running_management_commands_migrate:

Running migrate
***************

.. code-block:: console

    $ docker exec -it mrmap_gunicorn_1 python /opt/mrmap/manage.py migrate

.. _running_management_commands_makemessages:

Running makemessages
*********************

Makemessages should run local by calling:

.. code-block:: console

    $ python manage.py makemessages --locale=de

.. _running_management_commands_compilemessages:

Running compilemessages
***********************

Compilemessages should run local by calling:

.. code-block:: console

    $ python manage.py compilemessages --locale=de

.. _running_management_commands_tests:

Running Tests
=============

Throughout the course of development, it's a good idea to occasionally run MrMap's test suite to catch any potential errors. 
In our project there are two kinds of test suites which are used to test the hole project.

For deeper testing some code snippets we are using the default django test suite.

Tests are run using the ``django-test`` container which runs the django test suite for us:

.. code-block:: console

    $ docker compose -f ./docker-compose.yml -f ./docker-compose.dev.yml up --build django-test


To test the `json:api <https://jsonapi.org/>`_ we are using the `behave <https://behave.readthedocs.io/en/stable/>`_ suite with the `gherkin language <https://cucumber.io/docs/gherkin/reference/>`_.
You can run the test suite by starting the ``behave tests`` containter by using the following command:

.. code-block:: console

    $ docker compose -f ./docker-compose.yml -f ./docker-compose.dev.yml up --build django-test


Test documentation builds properly
==================================

.. warning::
    You need to have installed all python dependencies locally first. ``pip3 install -r ./mrmap/requirements.txt``

.. code-block:: console

    $ sphinx-multiversion docs/source docs/build/html -b linkcheck

.. code-block:: console

    $ sphinx-multiversion docs/source docs/build/html 

The documentation should be successfully build in the ``docs/build`` folder. Open the ``docs/build/index.html`` to test it.


Submitting Pull Requests
========================

Once you're happy with your work and have verified all steps described in :ref:`DoD <development-dod>` submit a `pull request <https://github.com/mrmap-community/mrmap/compare>`_ to the MrMap repo to propose the changes. Always provide descriptive (but not excessively verbose) commit messages. When working on a specific issue, be sure to reference it.

.. code-block:: console

    $ git commit -m "Closes #1234: Add wms support"
    $ git push origin

Be sure to provide a detailed accounting of the changes being made and the reasons for doing so.

Once submitted, a maintainer will review your pull request and either merge it or request changes. If changes are needed, you can make them via new commits to your branch: The pull request will update automatically.

.. note::
    Remember, pull requests are entertained only for **accepted** issues. If an issue you want to work on hasn't been approved by a maintainer yet, it's best to avoid risking your time and effort on a change that might not be accepted.
