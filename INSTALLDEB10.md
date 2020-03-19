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

        sudo apt install virtualenv
        
1. create virtualenv

        virtualenv -p python3 `PATH-TO-MAPSKINNER`/venv
        
> to use the virtualenv run: source `PATH-TO-MAPSKINNER`/venv/bin/activate

##Install apache2 with mapserver
> We use mapserver to produce the masks for spatial restrictions.
1. Install all needed packages:

        sudo apt install apache2 apache2-bin apache2-utils cgi-mapserver \
                     mapserver-bin mapserver-doc libmapscript-perl\
                     python-mapscript ruby-mapscript\
                     libcurl4-openssl-dev libssl-dev\
                     libapache2-mod-fcgid
                     
1. Enable cgi and fastcgi:

        sudo a2enmod cgi fcgid
        
1. Configure mapserver on default page (`/etc/apache2/sites-available/000-default.conf`):

        ScriptAlias /cgi-bin/ /usr/lib/cgi-bin/
        <Directory "/usr/lib/cgi-bin/">
            AllowOverride All
            Options +ExecCGI -MultiViews +FollowSymLinks
            AddHandler fcgid-script .fcgi
            Require all granted
        </Directory>
         
1. Restart apache2 daemon:

        sudo systemctl restart apache2
        
1. Proof mapserver installation:
    * type from terminal:
    
          mapserv -v
    * on the browser for cgi script http://localhost/cgi-bin/mapserv?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities that normally return the following message:
    
          msCGILoadMap(): Web application error. CGI variable "map" is not set.
          
##Install and setup postgresql
1. install all dependencies:
        
        sudo apt install postgresql postgresql-client postgis
        
1. login as postgres

        sudo su - postgres        
      
1. run postgres shell

        pysql
                
1. create db for mr. map:

        CREATE DATABASE "MrMap";

1. exit postgres shell and logout from postgres user

        exit
        exit

1. configure pg_hba.conf
    1. open the file under `/etc/postgresql/11/main/pg_hba.conf` with your preferred editor.
        
            sudo vim /etc/postgresql/11/main/pg_hba.conf 
    
    1. change authentication method to trust for all:
        ```vim
        # Database administrative login by Unix domain socket
        local   all             postgres                                trust
        
        # TYPE  DATABASE        USER            ADDRESS                 METHOD
        
        # "local" is for Unix domain socket connections only
        local   all             all                                     trust
        # IPv4 local connections:
        host    all             all             127.0.0.1/32            trust
        # IPv6 local connections:
        host    all             all             ::1/128                 trust
        # Allow replication connections from localhost, by a user with the
        # replication privilege.
        local   replication     all                                     trust
        host    replication     all             127.0.0.1/32            trust
        host    replication     all             ::1/128                 trust
        ```     
       
1. restart postgres daemon

        sudo systemclt restart postgresql