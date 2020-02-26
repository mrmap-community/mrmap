<img src="https://git.osgeo.org/gitea/hollsandre/MapSkinner/raw/branch/pre_master/structure/static/structure/images/mr_map.png" width="200">

## About
Mr. Map is a service registry for web map services ([WMS](https://www.opengeospatial.org/standards/wms)) 
and web feature services ([WFS](https://www.opengeospatial.org/standards/wfs)) as introduced by the 
Open Geospatial Consortium [OGC](http://www.opengeospatial.org/).

Since most GIS solutions out there are specified on a specific use case or aged without proper support, the need
for an open source, generic geospatial registry system is high.

Mr. Map is currently under development by the central spatial infrastructure of Rhineland-Palatinate 
([GDI-RP](https://www.geoportal.rlp.de/mediawiki/index.php/Zentrale_Stelle_GDI-RP)), Germany.


<img src="https://www.geoportal.rlp.de/static/useroperations/images/logo-gdi.png" width="200">

## Functionality
The system provides the following functionalities:

* User management
  * Create users and organize them in groups, supporting group hierarchy 
  * Configure group inherited permissions
  * Organize groups in organizations 
* Service management
  * Register web map services in all current versions (1.0.0 - 1.3.0)
  * Register web feature services in all current versions (1.0.0 - 2.0.2)
  * Create automatically organizations from service metadata
  * Generate Capabilities links to use in any map viewer which supports WMS/WFS imports
* Metadata Editor 
  * Edit describing service metadata such as titles, abstracts, keywords and so on
  * Edit describing metadata for every subelement such as map layers or feature types
  * Reset metadata on every level of service hierarchy
* Proxy
  * Mask service related links using an internal proxy 
     * tunnels `GetCapabilities` requests, `LegendURL`, `MetadataURL`, `GetMap`, `GetFeature` and more
* Secured Access
  * Restrict access to your service (public/private)
  * Allow access for certain groups of users
  * Draw geometries to allow access only in these spatial areas
* Publisher system
  * Allow other groups to register your services with reference on your organization
  * Revoke the permissions whenever you want 
* Dashboard
  * Have an overview on all newest activities of your groups, all your registered services or 
  pending publisher requests
* Catalogue and API
  * Find services using the catalogue JSON interface 
  * Have reading access to metadata, whole services, layers, organizations or groups
  


## Install:

We use Docker to run postgis and redis, so make sure Docker is installed on your system.
From within the project directory run

```shell
docker-compose -f docker/docker-compose.yml up
```

to install and start the services. Then, run following commands:

```shell
apt update  
apt install postgresql-server-dev-all libgdal-dev virtualenv python3-pip curl libgnutls28-dev cgi-mapserver

virtualenv -p python3 /opt/env
source /opt/env/bin/activate  
cd /opt/  
git clone https://git.osgeo.org/gitea/hollsandre/MapSkinner  
cd /opt/MapSkinner 
pip install -r requirements.txt  

python manage.py makemigrations service
python manage.py makemigrations structure
python manage.py makemigrations monitoring
python manage.py migrate  
```

## Initial setup:
1. Make sure the `HTTP_PROXY` variable in `MapSkinner/settings.py` is set correctly for your system
1. Call the setup command and follow the prompt instructions to generate the system's superuser and load default elements

```shell
python manage.py setup
```


## Important
Since the registration, deletion and perspectively a lot of other functionalities use an asynchronous worker approach, so the user won't have to wait until the last action finishes, the server always should have run this command before the usage:
```shell
celery -A MapSkinner worker -l info
```
If a task didn't finish due to reasons, you can delete the related **Pending task** record from the table.

## Dev Setup

After initialising the project, the development setup can be started as follows.
From within the project directory, run each of the following commands in a dedicated terminal:

```shell
docker-compose -f docker/docker-compose.yml up
celery -A MapSkinner worker -l info
python manage.py runserver_plus
celery -A MapSkinner beat -l info
```

### Dev Setup With GeoServer/MapServer

It is also possible to start the application with a containerized GeoServer or MapServer.
To do so, instead of 

```shell
docker-compose -f docker/docker-compose.yml up
```

Run

```shell
docker-compose -f docker/docker-compose-dev-geoserver.yml up
```

for including GeoServer (reachable at `localhost:8090/geoserver`), and

```shell
docker-compose -f docker/docker-compose-dev-mapserver.yml up
```

for including MapServer (reachable at `localhost:8091`).

GeoServer data will be mounted to `geoserver/geoserver_data`.

Mapfiles should be placed in `mapserver/mapfiles` and related data files in `mapserver/mapdata`.
Maps can then be accessed via `http://localhost:8091/?map=/etc/mapserver/MAPFILE.map` (replace `MAPFILE` with actual mapfile name).

## Production setup

**Note:** Before running the production setup, make sure you changed all default usernames and passwords,
disabled debugging, and verified the list of allowed hosts.

After initialising the project, the production setup can be started as follows.
From within the project directory, run each of the following commands in a dedicated terminal:

```shell
docker-compose -f docker/docker-compose.yml up 
celery -A MapSkinner worker -l info
python manage.py runserver
celery -A MapSkinner beat -l info
```
