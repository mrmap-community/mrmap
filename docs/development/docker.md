# Docker compose usage

All needed services you need to get up running a full MrMap instance are configured in the [docker-compose-dev.yml](https://github.com/mrmap-community/mrmap/blob/master/mrmap/docker/docker-compose-dev.yml) YAML configuration file.

| Dependency     | Minimum Version |
|----------------|-----------------|
| [docker](https://docs.docker.com/engine/install)         | 20              |
| [docker compose](https://docs.docker.com/compose/install) | 1.28            |


## Post-usage steps

1. Install [docker engine](https://docs.docker.com/engine/install) 
2. Install [docker compose](https://docs.docker.com/compose/install)

!!! warning
    Make sure that the user you running docker-compose from, has managing rights for docker. For linux developers see [Post-installation steps for Linux](https://docs.docker.com/engine/install/linux-postinstall/)

## Start services

You can start all configured services with the command `docker-compose -f docker-compose-dev.yml up --build`. After that, all services should be started properly.

## Running django commands

!!! warning
    Run the manage.py always with the docker specific settings from `MrMap.settings_docker.py` by passing the environment variable like `DJANGO_SETTINGS_MODULE=MrMap.settings_docker` as prefixed parameter for example.

### Start django runserver

To start the django build in runserver, run the command `DJANGO_SETTINGS_MODULE=MrMap.settings_docker python mrmap/manage.py runserver 0.0.0.0:8000`
After that you can access the django application by calling the `http://localhost:8000` url.

### Run django migration commands

the following commands should be run the first time, after docker-compose up:

**1. run migrate command:**

`DJANGO_SETTINGS_MODULE=MrMap.settings_docker python mrmap/manage.py migrate`

**2. run setup command:**

`DJANGO_SETTINGS_MODULE=MrMap.settings_docker python mrmap/manage.py setup`
