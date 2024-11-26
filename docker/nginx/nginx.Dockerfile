################################
# Base build Image
################################  
FROM node:23-alpine3.20 AS compile-image

# cause env variables are always not present
# in the docker build context, we need to set them explicitly.


WORKDIR /app

COPY ./frontend/ .

# Define build arguments for environment variables
ARG VITE_API_BASE_URL
ARG VITE_API_SCHEMA

# Set environment variables during the build process
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_SCHEMA=$VITE_API_SCHEMA


RUN npm install && \
  npm run build


################################
# Final Image
################################  
FROM nginx:1.27.2-alpine-slim AS production-image

COPY --from=compile-image /app/dist /usr/share/nginx/html
