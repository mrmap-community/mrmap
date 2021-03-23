# MrMap Installation

This section of the documentation discusses installing and configuring the MrMap application itself.

## Install System Packages

Begin by installing all system packages required by MrMap and its dependencies.

!!! note
    MrMap require Python 3.7, or 3.8.

### Debian

On debian 10 you have python3.7 available in the system packages, on other versions
 or distros you might have to compile it yourself.

```no-highlight
sudo apt install -y libcurl4-openssl-dev libssl-dev python3.7-dev gdal-bin virtualenv
```

### Initial setup Mr. Map (virtualenv way)

1. clone the project from the repo to your preferred install directory:

        cd `INSTALL-DIR`, e.g: /opt/
        git clone https://github.com/mrmap-community/mrmap

1. create your virtualenv and activate it:

        virtualenv -ppython3.7 `PATH-TO-YOUR-VENV`, e.g: /opt/mrmap/venv
        source `PATH-TO-YOUR-VENV`/bin/activate

1. install all requirements in to the virtualenv:

        (venv) $ python -m pip install -r `INSTALL-DIR`/mrmap/requirements.txt

1. set database parameters in `INSTALL-DIR`/mrmap/MrMap/sub_settings/db_settings.py

        ...
        'USER': 'mrmap',
        'PASSWORD': 'J5brHrAXFLQSif0K',
        ...

1. run django migrations:

        (venv) $ python `INSTALL-DIR`/mrmap/manage.py migrate

1. (Optional) Configure proxy:

    Make sure the HTTP_PROXY variable in MrMap/settings.py is set correctly for your system

1. run setup routine to get initialized db with admin user for mr. map:

        (venv) $ python `INSTALL-DIR`/mrmap/manage.py setup

### Start up everything we need
!!! note
    all following commands are run within the project root directory run by using your virtual env.
    you can run the commands in background by adding a trailing &

1. start up celery process (celery will do async jobs for us)

        (venv) $ cd  `INSTALL-DIR`/mrmap/
        (venv) $ celery -A MrMap worker -l INFO

1. start up celery beat process

        (venv) $ celery -A MrMap beat -l INFO

1. start up mr. map

        (venv) $ python manage.py runserver_plus 0.0.0.0:8000
!!! note
   [runserver_plus](https://django-extensions.readthedocs.io/en/latest/runserver_plus.html) gives us more debug informations


1. you should see the login page after opening http://127.0.0.1:8000 or http://YOUR-IP-ADDRESS:8000:

    ![login page](../installation/mrmap_loginpage.png)

You can now login with the user you configured in your python manage.py setup routine.
