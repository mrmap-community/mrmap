################################
# Base build Image
################################  
FROM python:3.9.7-bullseye AS base
ARG MRMAP_PRODUCTION
RUN apt-get -qq update && \
    apt-get -y install --no-install-recommends gcc libssl-dev gdal-bin npm
    
# build python dependencies    
COPY ./requirements.txt /
RUN if [ "${MRMAP_PRODUCTION}" = "False" ] ; then echo "\ndebugpy==1.4.3\ncoverage==5.5" >> requirements.txt; fi && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

# download front end dependencies
COPY ./package.json /
RUN npm install --yes

################################
# MrMap Image
################################    
FROM python:3.9.7-slim-bullseye
COPY --from=base /wheels /wheels
COPY --from=base requirements.txt .
COPY --from=base node_modules/bootstrap/dist/css/bootstrap.min.css node_modules/animate.css/animate.min.css /tmp/mrmap/static/css/
COPY --from=base node_modules/bootstrap/dist/js/bootstrap.min.js node_modules/popper.js/dist/popper.min.js node_modules/jquery/dist/jquery.min.js /tmp/mrmap/static/js/

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