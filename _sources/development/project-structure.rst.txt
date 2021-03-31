.. _development-project-structure:


=================
Project Structure
=================


All development of the current MrMap release occurs in the ``develop`` branch; releases are packaged from the ``master`` branch. The ``master`` branch should `always` represent the current stable release in its entirety, such that installing MrMap by either downloading a packaged release or cloning the ``master`` branch provides the same code base.


MrMap apps
**********

MrMap components are arranged into functional subsections called `apps` (a carryover from Django vernacular). Each app holds the models, views, and templates relevant to a particular function:

* ``users``: Customize the Django authentication system
* ``structure``: todo
* ``service``: todo
* ``quality``: todo
* ``monitoring``: todo
* ``editor``: todo
* ``csw``: todo
* ``breadcrumb``: todo
* ``api``: todo
