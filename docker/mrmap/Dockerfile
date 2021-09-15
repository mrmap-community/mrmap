# debian 11 image
FROM python:3.9.7-bullseye AS base
ARG install_debugpy
RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends gcc libssl-dev gdal-bin
    
COPY ./mrmap/requirements.txt /
RUN if [ "${install_debugpy}" = "True" ] ; then echo "\ndebugpy==1.4.3" >> requirements.txt ; fi && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt
################################    
FROM python:3.9.7-slim-bullseye
COPY --from=base /wheels /wheels
COPY --from=base requirements.txt .

RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends libssl-dev gdal-bin libpq-dev netcat && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache --no-cache-dir /wheels/* && \
    rm -r /wheels

# set work directory
WORKDIR /opt/mrmap

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1


# run entrypoint.sh
ENTRYPOINT ["/opt/mrmap/entrypoint.sh"]