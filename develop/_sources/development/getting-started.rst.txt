.. _development-getting-started:


===============
Getting Started
===============

.. warning::
    **pre-condition**: run :ref:`installation guide <installation>` first before you start working on this section.

Cause MrMap is full dockerized, the development of it is priciple possible on any operating system. Feel free to use the development ide of your choice.

We provide configuration files for `pycharm <https://www.jetbrains.com/de-de/pycharm/>`_ and `vscode <https://code.visualstudio.com/>`_. 

* To configure pycharm see :ref:`documentation <development-pycharm-cfg>`
* To configure vscode see :ref:`documentation <development-vscode-cfg>`

 
Branch structure
================

The MrMap project utilizes three persistent git branches to track work:

* ``master`` - Serves as a snapshot of the current stable release
* ``develop`` - Tracks work on an upcoming new minor release
* ``feature`` - Tracks work on an upcoming new feature

Typically, you'll base pull requests off of the ``develop`` branch, or off of ``feature`` if you're working on a new major release. **Never** merge pull requests into the ``master`` branch, which receives merged only from the ``develop`` branch.

Enable Pre-Commit Hooks
=======================

MrMap ships with a `git pre-commit hook <https://githooks.com/>`_ script that automatically checks for style compliance and missing database migrations prior to committing changes. This helps avoid erroneous commits that result in CI test failures. You are encouraged to enable it by creating a link to ``scripts/git-hooks/pre-commit``:

.. code-block:: console

    $ cd .git/hooks/
    $ ln -s ../../scripts/git-hooks/pre-commit

Running Tests
=============

Throughout the course of development, it's a good idea to occasionally run MrMap's test suite to catch any potential errors. Tests are run using the ``test`` management command:

.. code-block:: console

    $ python ./mrmap/manage.py test


In cases where you haven't made any changes to the database (which is most of the time), you can append the ``--keepdb`` argument to this command to reuse the test database between runs. This cuts down on the time it takes to run the test suite since the database doesn't have to be rebuilt each time. (Note that this argument will cause errors if you've modified any model fields since the previous test run.)

.. code-block:: console

    $ python ./mrmap/manage.py test --keepdb


Test documentation builds properly
==================================

.. note::
    Install python dependencies local first. `pip3 install -r ./mrmap/requirements.txt && pip3 install -r ./mrmap/docs/requirements.txt`

.. code-block:: console

    $ cd docs/
    $docs/ export $(grep -v '^#' ../.env.mrmap | xargs)
    $docs/ make clean
    $docs/ make linkcheck
    $docs/ make html


Submitting Pull Requests
========================

Once you're happy with your work and have verified that all tests pass, commit your changes and push it upstream to your fork. Always provide descriptive (but not excessively verbose) commit messages. When working on a specific issue, be sure to reference it.

.. code-block:: console

    $ git commit -m "Closes #1234: Add wms support"
    $ git push origin


Once your fork has the new commit, submit a `pull request <https://github.com/mrmap-community/mrmap/compare>`_ to the MrMap repo to propose the changes. Be sure to provide a detailed accounting of the changes being made and the reasons for doing so.

Once submitted, a maintainer will review your pull request and either merge it or request changes. If changes are needed, you can make them via new commits to your fork: The pull request will update automatically.

.. note::
    Remember, pull requests are entertained only for **accepted** issues. If an issue you want to work on hasn't been approved by a maintainer yet, it's best to avoid risking your time and effort on a change that might not be accepted.
