# Mapserver Installation

## Install Mapserver

[Mapserver](https://redis.io/) is an in-memory key-value store which NetBox employs for caching and queuing. This section entails the installation and configuration of a local Redis instance. If you already have a Redis service in place, skip to [the next section](3-netbox.md).

!!! note
    MrMap require Redis v4.0 or higher. If your distribution does not offer a recent enough release, you will need to build Redis from source. Please see [the Redis installation documentation](https://github.com/redis/redis) for further details.

### Debian

```no-highlight
sudo apt install -y nginx cgi-mapserver fcgiwrap
```

## Configure Mapserver:

Open file `/etc/nginx/sites-available/default` and add the following location:

```
        location /cgi-bin/ {
   		gzip off;
		root  /usr/lib;
		fastcgi_pass  unix:/var/run/fcgiwrap.socket;
		include /etc/nginx/fastcgi_params;
		fastcgi_param SCRIPT_FILENAME  $document_root$fastcgi_script_name;
        }
```

## Verify Service Status

1. Use the `mapserv` utility to ensure the Mapserver service is functional:

```no-highlight
$ mapserv -v
MapServer version 7.2.2 OUTPUT=PNG OUTPUT=JPEG OUTPUT=KML SUPPORTS=PROJ SUPPORTS=AGG SUPPORTS=FREETYPE SUPPORTS=CAIRO SUPPORTS=SVG_SYMBOLS SUPPORTS=RSVG SUPPORTS=ICONV SUPPORTS=FRIBIDI SUPPORTS=WMS_SERVER SUPPORTS=WMS_CLIENT SUPPORTS=WFS_SERVER SUPPORTS=WFS_CLIENT SUPPORTS=WCS_SERVER SUPPORTS=SOS_SERVER SUPPORTS=FASTCGI SUPPORTS=THREADS SUPPORTS=GEOS SUPPORTS=PBF INPUT=JPEG INPUT=POSTGIS INPUT=OGR INPUT=GDAL INPUT=SHAPEFILE
```

2. Open the browser and go to http://localhost/cgi-bin/mapserv?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities
You should see the following message:
   
```no-highlight
    msCGILoadMap(): Web application error. CGI variable "map" is not set.
```