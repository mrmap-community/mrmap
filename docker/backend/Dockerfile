################################
# Base build Image
################################  
FROM python:3.10.1-bullseye AS compile-image
ARG MRMAP_PRODUCTION
RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends gcc libssl-dev gdal-bin

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# build python dependencies    
COPY ./requirements.txt ./requirements.dev.txt /
RUN /usr/local/bin/python -m pip install --upgrade pip && \
    pip install -r requirements.txt
RUN if [ "${MRMAP_PRODUCTION}" = "False" ] ; then pip install -r requirements.dev.txt; fi

################################
# MrMap Image
################################    
FROM python:3.10.8-slim-bullseye as runtime-image
ARG MRMAP_PRODUCTION
COPY --from=compile-image /opt/venv /opt/venv

# TODO: gettext are only needed for dev environment
RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends libssl-dev gdal-bin libpq-dev netcat libyaml-dev gettext && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# set work directory
WORKDIR /opt/mrmap

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8001/tcp