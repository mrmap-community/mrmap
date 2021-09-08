# debian 11 image
FROM python:3-bullseye

ENV MRMAP_PATH /opt/mrmap
ENV MANAGE_PY $MRMAP_PATH/manage.py
ENV MRMAP_REQ $MRMAP_PATH/requirements.txt
#WORKDIR ./app

# todo check if all this packages are still needed...
RUN apt-get -qq update && \
    apt-get -y install iputils-ping libcurl4-openssl-dev libssl-dev gdal-bin libpq-dev gcc

# copy code base
#VOLUME . $MRMAP_PATH
COPY . $MRMAP_PATH
RUN chmod +x $MRMAP_PATH/start.sh

RUN pip install -r $MRMAP_REQ

RUN python $MANAGE_PY collectstatic -c --noinput

CMD ["/opt/mrmap/start.sh"]