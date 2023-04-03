################################
# Base build Image
################################  
FROM python:3.11.2-alpine3.17 AS compile-image
ARG MRMAP_PRODUCTION
RUN apk update && \
    apk add --no-cache build-base libressl-dev gdal

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# build python dependencies    
COPY ./requirements.txt /
COPY ./.requirements /.requirements
RUN /usr/local/bin/python -m pip install --upgrade pip && \
    pip install -r requirements.txt
RUN if [ "${MRMAP_PRODUCTION}" = "True" ] ; then pip uninstall -r ./requirements/dev.txt && pip uninstall -r ./requirements/docs.txt; fi

################################
# MrMap Image
################################    
FROM python:3.11.2-alpine3.17 as runtime-image
ARG MRMAP_PRODUCTION
COPY --from=compile-image /opt/venv /opt/venv

# TODO: gettext are only needed for dev environment
RUN apk update
RUN apk add --no-cache libpq netcat-openbsd yaml gettext gdal geos libressl
#RUN apk cache clean
RUN rm -rf /var/cache/apk/*

# set work directory
WORKDIR /opt/mrmap

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8001/tcp

ENTRYPOINT [ "/opt/mrmap/.bash_scripts/entrypoint.sh" ]
CMD [ "gunicorn -b 0.0.0.0:8001 -k uvicorn.workers.UvicornWorker --workers=4 --reload --log-level=info --timeout=0 MrMap.asgi:application" ]