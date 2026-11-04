#!/bin/sh
# Lockfile-aware dependency bootstrap for the frontend-tests service
# (issue #963, epic #959). Seed /opt/mrmap/frontend/node_modules - the
# project-scoped volume mounted there by compose - from the dependency tree
# baked into /opt/frontend-deps by docker/frontend/tests.Dockerfile, instead
# of running `npm ci` on every container start.
#
# The fingerprint marker lives inside node_modules itself, so it shares its
# lifetime with the modules: an updated package.json/package-lock.json changes
# the current fingerprint, the stale volume is detected and either re-seeded
# from a matching image or replaced by a real `npm ci`. Modules can never
# silently go stale. When no dependency tree is baked into the image (plain
# node:26-alpine, the non-prebuilt path) the script does nothing.
set -eu

APP_DIR=/opt/mrmap/frontend
DEPS_DIR=/opt/frontend-deps
NM_DIR="$APP_DIR/node_modules"
MARKER="$NM_DIR/.mrmap-deps-fp"

if [ ! -d "$DEPS_DIR/node_modules" ]; then
    exec "$@"
fi

current_fp=$({ cat "$APP_DIR/package.json" "$APP_DIR/package-lock.json"; node -v; npm -v; } | sha256sum | cut -d ' ' -f1 | cut -c1-12)

if [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$current_fp" ]; then
    echo "frontend-deps: node_modules volume is up to date (fp $current_fp)" >&2
else
    image_fp=$(cat "$DEPS_DIR/.mrmap-deps-fp" 2>/dev/null || echo none)
    if [ "$image_fp" = "$current_fp" ]; then
        echo "frontend-deps: seeding node_modules from image (fp $current_fp)" >&2
        mkdir -p "$NM_DIR"
        find "$NM_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
        cp -a "$DEPS_DIR/node_modules/." "$NM_DIR/"
    else
        echo "frontend-deps: mounted lockfile ($current_fp) differs from image ($image_fp) - running npm ci" >&2
        ( cd "$APP_DIR" && npm ci --no-audit --no-fund )
    fi
    echo "$current_fp" > "$MARKER"
fi

exec "$@"
