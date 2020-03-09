<img src="https://git.osgeo.org/gitea/hollsandre/MapSkinner/raw/branch/pre_master/MapSkinner/static/images/mr_map.png" width="200">

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

We use mapserver to produce the masks for spatial restrictions, so we have to install apache2 and mapserv:

### Install apache2 with mapserver
(1.) Install the packages
```shell
apt-get install apache2 apache2-bin apache2-utils cgi-mapserver \
                     mapserver-bin mapserver-doc libmapscript-perl\
                     python-mapscript ruby-mapscript
```
(2.) Enable cgi and fastcgi
```shell
a2enmod cgi fcgid
```
(3.) on Apache2 configuration file (e.g. /etc/apache2/sites-available/000-default.conf) add the following lines:
```shell
         ScriptAlias /cgi-bin/ /usr/lib/cgi-bin/
         <Directory "/usr/lib/cgi-bin/">
                 AllowOverride All
                 Options +ExecCGI -MultiViews +FollowSymLinks
                 AddHandler fcgid-script .fcgi
                 Require all granted
         </Directory>
```
(4.) restart apache2 daemon
```shell
service apache2 restart
```
(5.) check mapserver install
* typing from terminal:
```shell
mapserv -v 
```
* on the browser for cgi script http://localhost/cgi-bin/mapserv?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities that normally return the following message:
```shell
msCGILoadMap(): Web application error. CGI variable "map" is not set.
```

### Docker
We use Docker to run postgis and redis, so make sure Docker is installed on your system.
>
Install note for Debian 9: 
##### Install docker
* add apt-key:
```shell
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo apt-key add -
```
```shell
apt-key fingerprint 0EBFCD88
```
* add apt-repo: 
```shell
add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/debian \ 
$(lsb_release -cs) \ 
stable"
```
* run update: 
```shell
apt-get update
```
* install docker: 
```shell
apt-get install docker-ce docker-ce-cli containerd.io
```
* test docker daemon: 
```shell
docker run hello-world
```
##### Proxy settings (Only if you got one in your environment)
* add new file */etc/systemd/system/docker.service.d/http-proxy.conf* with following content:
```vim
[Service]
Environment="HTTP_PROXY=http://user:password@proxy:port"
Environment="HTTPS_PROXY=http://user:password@proxy:port"
```
##### Install docker-compose
* Install docker-compose from pip to get the version >1.25 
* add your user to the group *docker* to get the right permissions to access docker daemon: usermod -aG docker *username*
>
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
python manage.py migrate  
```

## Initial setup:
1. Make sure the `HTTP_PROXY` variable in `MapSkinner/settings.py` is set correctly for your system
1. Call the setup command and follow the prompt instructions to generate the system's superuser and load default elements

```shell
python manage.py setup
```


## Important
### Background worker
Since the registration, deletion and perspectively a lot of other functionalities use an asynchronous worker approach, so the user won't have to wait until the last action finishes, the server always should have run this command before the usage:
```shell
celery -A MapSkinner worker -l info
```
If a task didn't finish due to reasons, you can delete the related **Pending task** record from the table.

### Dockerfile changes
If you are going to change the **database** settings, which are set in `docker-compose.yml`, you have to change the 
settings for the variable `CONNECTION` in `/service/mapserver/security_mask.map` as well. 
```
CONNECTION "host=localhost dbname=mapskinner user=postgres password=postgres port=5555"
```

## Dev Setup

After initialising the project, the development setup can be started as follows.
From within the project directory, run:

```shell
docker-compose -f docker/docker-compose.yml up
celery -A MapSkinner worker -l info
python manage.py runserver_plus
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
From within the project directory, run:

```shell
docker-compose -f docker/docker-compose.yml up 
celery -A MapSkinner worker -l info
python manage.py runserver
```
