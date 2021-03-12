# Installation

The installation instructions provided here have been tested to work on Debian 10. The particular commands needed to install dependencies on other distributions may vary significantly. Unfortunately, this is outside the control of the MrMap maintainers. Please consult your distribution's documentation for assistance with any errors.
Take a look at the [instructions](https://git.osgeo.org/gitea/GDI-RP/MrMap/src/branch/pre_master/install) in the install folder on how to deploy the project on a production system.

The following sections detail how to set up a new instance of MrMap:

1. [PostgreSQL database](1-postgresql.md)
1. [Redis](2-redis.md)
1. [Mapserver](3-mapserver.md)
1. [MrMap components](4-mrmap.md)


## Requirements

| Dependency | Minimum Version |
|------------|-----------------|
| Python     | 3.7             |
| PostgreSQL | 11.10           |
| Redis      | 5.0.3           |

Below is a simplified overview of the MrMap application stack for reference:

![MrMap UI as seen by a non-authenticated user](../media/installation/mrmap_application_stack.png)