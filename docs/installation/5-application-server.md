# uWSGI

## Install

We use [uWSGI server](https://uwsgi-docs.readthedocs.io) for serving the application.

!!! note
    You can also use other popular wsgi application servers such as [gunicorn](https://gunicorn.org ).

1. If you use a virtualenv, activate it before installing uwsgi

```no-highlight
source /opt/mrmap/venv/bin/activate
(venv) python -m pip install uwsgi
```

## Configure

1. Adjust if needed and copy the config files to their destination:  
We need a [ini file for uwsgi](https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_uwsgi_ini)  
and a [service definition for uwsgi](https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_uwsgi_service)

!!! note
    If you are using a virtualenv, you have to change the path to the uwsgi binary in [uwsgi service file](https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_uwsgi_service)
    to the one in the virtualenv eg. "/opt/mrmap/venv/bin/uwsgi"  
    If your installation directory differs from /opt/, you have to change it in the [ini file for uwsgi](https://github.com/mrmap-community/mrmap/blob/master/install/confs/mrmap_uwsgi_ini)  


```no-highlight
# copy uwsgi ini
cp -a /opt/mrmap/mrmap/install/confs/mrmap_uwsgi_ini /opt/mrmap/mrmap/MrMap/mrmap_uwsgi.ini
# copy uwsgi systemd config (service file)
cp -a /opt/mrmap/mrmap/install/confs/mrmap_uwsgi_service /etc/systemd/system/uwsgi.service
```

1. Create directory for pid file according to mrmap_uwsgi.ini

```no-highlight
sudo mkdir /var/run/uwsgi
sudo chown www-data /var/run/uwsgi
```

1. Activate and start uwsgi service

```no-highlight
sudo systemctl enable uwsgi
sudo systemctl start uwsgi
```

## Verify Service Status

1. Check the output of

```no-highlight
sudo systemctl status uwsgi
```
