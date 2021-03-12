# MrMap Installation

This section of the documentation discusses installing and configuring the MrMap application itself.

## Install System Packages

Begin by installing all system packages required by MrMap and its dependencies.

!!! note
    MrMap require Python 3.7, or 3.8.

### Debian

```no-highlight
sudo apt install -y libcurl4-openssl-dev libssl-dev python3.7-dev gdal-bin virtualenv
```

!!! note
    To use the virtualenv run: source `PATH-TO-MrMap`/venv/bin/activate


Before continuing with either platform, update pip (Python's package management tool) to its latest release:

```no-highlight
sudo pip3 install --upgrade pip
```

### Initial setup Mr. Map
1. activate your configured virtualenv:
        
        $ source `PATH-TO-YOUR-VENV`/bin/activate

1. clone the project from the repo to your preferred install directory:
        
        (venv) $ cd `INSTALL-DIR`
        (venv) $ git clone https://git.osgeo.org/gitea/GDI-RP/MrMap 
   
!!! note
    all following commands are from within the project root directory run.

1. install all requirements:

        (venv) $ pip install -r requirements.txt
        
1. run django migrations:

        (venv) $ python manage.py migrate

1. (Optional) Configure proxy:
    
    Make sure the HTTP_PROXY variable in MrMap/settings.py is set correctly for your system

1. run setup routine to get initialized db with admin user for mr. map:
        
        (venv) $ python manage.py setup
        
### Start up everything we need
!!! note
    all following commands are run within the project root directory run by using your virtual env.
       
1. start up celery process (celery will do async jobs for us)

        (venv) $ celery -A MrMap worker -l INFO
        
1. start up mr. map

        (venv) $ python manage.py runserver_plus
!!! note
   [runserver_plus](https://django-extensions.readthedocs.io/en/latest/runserver_plus.html) gives us more debug informations

1. start up celery beat process

        (venv) $ celery -A MrMap beat -l INFO
   

1. you should see the login page after opening http://127.0.0.1:8000:

    ![login page](../installation/mrmap_loginpage.png)
    
You can now login with the user you configured in your python manage.py setup routine.