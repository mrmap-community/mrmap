# debian 11 image
FROM python:3.9.7-bullseye as base
# todo check if all this packages are still needed...
ARG install_debugpy
RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends gcc
COPY requirements.txt /
RUN if [ "${install_debugpy}" = "True" ] ; then echo "\ndebugpy==1.4.3" >> requirements.txt ; fi && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

FROM python:3.9.7-slim-bullseye
ARG ENV
COPY --from=base /wheels /wheels
COPY --from=base requirements.txt .
RUN apt-get -qq update && \
    apt-get -y install libssl-dev gdal-bin libpq-dev netcat && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache --no-cache-dir /wheels/*

# set work directory
WORKDIR /opt/mrmap

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# run entrypoint.sh
ENTRYPOINT ["/opt/mrmap/entrypoint.sh"]