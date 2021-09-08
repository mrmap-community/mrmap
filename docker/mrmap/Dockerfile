# debian 11 image
FROM python:3-bullseye

ENV MRMAP_PATH /opt/mrmap
ENV MANAGE_PY $MRMAP_PATH/manage.py
ENV MRMAP_REQ $MRMAP_PATH/requirements.txt
#WORKDIR ./app

# todo check if all this packages are still needed...
RUN apt-get -qq update && \
    apt-get -y install iputils-ping libcurl4-openssl-dev libssl-dev gdal-bin libpq-dev gcc

# By copying over requirements first, we make sure that Docker will cache
# our installed requirements rather than reinstall them on every build
COPY ./requirements.txt $MRMAP_REQ

# copy code base
COPY . $MRMAP_PATH

RUN pip install -r $MRMAP_REQ
RUN ping db
RUN python $MANAGE_PY makemigrations
RUN python $MANAGE_PY setup

# EXPOSE 8000

CMD ["$MRMAP_PATH/start.sh"]
#ENV DJANGO_SETTINGS_MODULE="MrMap.settings_docker"
#CMD ["python", "/mrmap/manage.py", "runserver", "0.0.0.0:8000"]