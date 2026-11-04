################################
# Dependency build image
################################
# Installs the npm dependencies only. The frontend source tree never enters
# this image - it arrives over the ./frontend bind mount of the compose files.
# The expensive layer depends on nothing but package.json and package-lock.json
# (and the base image), so ordinary source changes never invalidate it and a
# lockfile change always does. See docker-compose.prebuilt-frontend.yml for
# the runtime side and the epic #959 image contract for the fp tag scheme.
FROM node:26-alpine AS deps-image

WORKDIR /opt/deps
COPY ./frontend/package.json ./frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund \
    && { cat package.json package-lock.json; node -v; npm -v; } | sha256sum | cut -d ' ' -f1 | cut -c1-12 > /opt/deps-fp

################################
# Frontend test image
################################
FROM node:26-alpine AS runtime-image

# The dependency tree plus its fingerprint, kept OUTSIDE /opt/mrmap so the
# ./frontend bind mount cannot shadow it. The bootstrap script seeds the
# per-project node_modules volume from this copy and refuses to do so when the
# mounted lockfile does not match the baked fingerprint.
COPY --from=deps-image /opt/deps/node_modules /opt/frontend-deps/node_modules
COPY --from=deps-image /opt/deps-fp /opt/frontend-deps/.mrmap-deps-fp
COPY ./docker/frontend/tests-entrypoint.sh /usr/local/bin/mrmap-frontend-bootstrap

ENTRYPOINT ["/usr/local/bin/mrmap-frontend-bootstrap"]
