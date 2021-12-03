################################
# Base build Image
################################  
FROM python:3.9.7-bullseye AS base
ARG MRMAP_PRODUCTION
RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends gcc libssl-dev gdal-bin

# build python dependencies    
COPY ./requirements.txt ./requirements.dev.txt /
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt
RUN if [ "${MRMAP_PRODUCTION}" = "False" ] ; then pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.dev.txt; fi

################################
# MrMap Image
################################    
FROM python:3.9.7-slim-bullseye
ARG MRMAP_PRODUCTION
COPY --from=base /wheels /wheels

# TODO: gettext are only needed for dev environment
RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends libssl-dev gdal-bin libpq-dev netcat libyaml-dev gettext wget && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache --no-cache-dir /wheels/* && \
    rm -r /wheels

# set work directory
WORKDIR /opt/mrmap

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1