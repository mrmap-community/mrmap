##############################################################
# Base build Image for Frontend
##############################################################
FROM node:26-alpine3.24 AS frontend-compile-image

ARG VITE_API_BASE_URL
ARG VITE_API_PORT
ARG VITE_API_SCHEMA
# The exact revision of this bundle, stamped by the builder from .env; empty
# keeps the build a "dev revision" in the About display (#1579).
ARG MRMAP_BUILD_REVISION=""

WORKDIR /app

COPY ./frontend/ .

# The canonical application version (#1579): vite.config.mjs reads it at
# ../VERSION, i.e. exactly this /VERSION for this /app. The COPY is also the
# cache key: a version bump rebuilds the bundle, the same mechanism #1027
# learned for the API address args below.
COPY ./VERSION /VERSION

# The VITE_API_* args (docker-compose.yml derives them from EXTERNAL_BASE_URL /
# EXTERNAL_PORT / EXTERNAL_SCHEME) are baked into the bundle by `vite build`,
# which reads them from this RUN's environment. Echoing them in the command is
# not decoration: a build ARG is only guaranteed to be part of the cache key of
# the instruction that references it, so naming them here is what makes a
# changed address in .env rebuild the bundle on every builder (#1027). Before
# #922 removed the frontend-static volume no rebuild reached the browser at
# all; that the volume is gone is guarded by scripts/static_mounts_smoke.py.
RUN echo "building the SPA against ${VITE_API_SCHEMA}://${VITE_API_BASE_URL}:${VITE_API_PORT} (version $(tr -d '[:space:]' < /VERSION), revision ${MRMAP_BUILD_REVISION:-dev})" && \
  npm install

# The build is its own instruction so that a version or revision change busts
# the bundle cache without redoing the dependency install.
RUN MRMAP_BUILD_REVISION="${MRMAP_BUILD_REVISION}" npm run build


##############################################################
# Base build Image for Backend
##############################################################

FROM python:3.15.2-alpine3.24 AS backend-compile-image
ARG MRMAP_PRODUCTION

RUN apk update && \
  apk add --no-cache build-base gdal libressl-dev 

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY ./backend ./

RUN /usr/local/bin/python -m pip install --upgrade pip && \
  pip install -r requirements.txt && \
  python manage.py collectstatic 

##############################################################
# Final Image
##############################################################  
FROM nginx:1.31.10-alpine-slim AS production-image

COPY --from=frontend-compile-image /app/dist /var/www/mrmap/frontend/
COPY --from=backend-compile-image ./static /var/www/mrmap/backend/

# report browser side errors into the central log stack; the script is plain
# JS, not app code, and is injected *before* the app bundle so that it also
# catches the bundle and its chunks failing to load. Its own src is absolute
# (as are the built app references since the vite base fix for #941), so on any
# route the beacon still loads and reports what failed.
COPY docker/nginx/error-beacon.js /var/www/mrmap/frontend/error-beacon.js
RUN sed -i 's|<script type="module"|<script src="/error-beacon.js"></script><script type="module"|' /var/www/mrmap/frontend/index.html && \
  grep -q 'src="/error-beacon.js"' /var/www/mrmap/frontend/index.html

# the mrmap_frontend_error log of mrmap.conf is a file of its own, ship it to
# stdout exactly like the access.log of this image
RUN ln -s /dev/stdout /var/log/nginx/frontend-error.log

EXPOSE 80/tcp
EXPOSE 443/tcp