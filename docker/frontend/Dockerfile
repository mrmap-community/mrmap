FROM node:16-alpine

WORKDIR /opt/mrmap

COPY ./package.json .

# remove "--force" as soon as dependency issues with react-geo and react 17 have been resolved (https://github.com/mrmap-community/mrmap/issues/306)
RUN npm --force install
