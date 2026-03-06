##############################################################
# Base build Image for Frontend
##############################################################
FROM node:25-alpine3.23 AS frontend-compile-image

ARG VITE_API_BASE_URL
ARG VITE_API_PORT
ARG VITE_API_SCHEMA

WORKDIR /app

COPY ./frontend/ .

RUN npm install && \
  npm run build


##############################################################
# Base build Image for Backend
##############################################################

FROM python:3.12.13-alpine3.23 AS backend-compile-image
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
FROM nginx:1.29.5-alpine-slim AS production-image

COPY --from=frontend-compile-image /app/dist /var/www/mrmap/frontend/
COPY --from=backend-compile-image ./static /var/www/mrmap/backend/

EXPOSE 80/tcp
EXPOSE 443/tcp