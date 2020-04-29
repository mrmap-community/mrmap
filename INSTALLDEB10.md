#Installation instructions for debian 10
> tested on fresh Debian GNU/Linux 10 (buster) with 
> * python 3.7.3 
> * pip 20.0.2
> * MapServer version 7.2.2

##Install dependencies for some pip packages:
```bash
sudo apt install libcurl4-openssl-dev libssl-dev python3.7-dev gdal-bin
```

##Install and configure virtualenv
1. Install virtualenv

        $ sudo apt install virtualenv
        
1. create virtualenv

        $ virtualenv -p python3 `PATH-TO-MAPSKINNER`/venv
        
> to use the virtualenv run: source `PATH-TO-MAPSKINNER`/venv/bin/activate

##Install nginx with mapserver
We use mapserver to produce the masks for spatial restrictions.  

1. Install all needed packages:

        $ sudo apt install cgi-mapserver nginx fcgiwrap
                     
        
1. Configure mapserver on default page (`/etc/nginx/sites-available/default`):
```
        location /cgi-bin/ {
   		gzip off;
		root  /usr/lib;
		fastcgi_pass  unix:/var/run/fcgiwrap.socket;
		include /etc/nginx/fastcgi_params;
		fastcgi_param SCRIPT_FILENAME  $document_root$fastcgi_script_name;
        }
```
         
1. Restart nginx:

        $ sudo systemctl restart nginx
        
1. Verify mapserver installation:
    * type from terminal:
          $ mapserv -v
    * Open the browser and go to http://localhost/cgi-bin/mapserv?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities   
        You should see the following message:
    
          msCGILoadMap(): Web application error. CGI variable "map" is not set.
          
##Install and setup postgresql
1. install all dependencies:
        
        $ sudo apt install postgresql postgresql-client postgis
        
1. login as postgres

        $ sudo su - postgres        
      
1. run postgres shell

        $ psql
                
1. create db for mr. map:

        postgres=# CREATE DATABASE "MrMap";

1. exit postgres shell and logout from postgres user

        postgres=# exit
        $ exit

1. configure pg_hba.conf
    1. open the file under `/etc/postgresql/11/main/pg_hba.conf` with your preferred editor.
        
            $ sudo vim /etc/postgresql/11/main/pg_hba.conf 
    
    1. change authentication method to trust for local IPv4 connections, line 92 on a fresh prostgres installation:
        ```vim
        ...
        # IPv4 local connections:
        host    all             all             127.0.0.1/32            trust
        ...
        ```
             
       
1. restart postgres daemon

        $ sudo systemclt restart postgresql
        
##Install and Configuring Redis
1. install redis
        
        $ sudo apt install redis-server
        
1. open `/etc/redis/redis.conf`:

        $ sudo vim /etc/redis/redis.conf
        
1. configure systemd as supervised:

   * find line `supervised no` and change it to `supervised systemd`
   
1. restart redis:

        $ sudo systemctl restart redis
        
 1. test redis:
 
    * run redis cli:
         
          $ redis-cli    
          
    * test redis:
    
          127.0.0.1:6379> ping
          
          Output:
          PONG
          
    * exit:
          
          127.0.0.1:6379> exit