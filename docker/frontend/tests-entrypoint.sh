#!/bin/sh
# Lockfile-aware dependency bootstrap for the frontend-tests service
# (issue #963, epic #959; canonical fingerprint wiring by #962). Seed
# /opt/mrmap/frontend/node_modules - the project-scoped volume mounted there
# by compose - from the dependency tree baked into /opt/frontend-deps by
# docker/frontend/tests.Dockerfile, instead of running `npm ci` on every
# container start.
#
# Two fingerprints (the sync contract of #962, documented in
# scripts/dev_image_id.py):
#   * deps fp - sha256 over package.json + package-lock.json + node -v + npm -v.
#     The image bakes it into /opt/frontend-deps/.mrmap-deps-fp and it depends
#     on nothing but the installed tree, so it alone decides whether the
#     image's modules match the mounted lockfiles.
#   * canonical image fp - the immutable tag of the image, resolved on the
#     host by scripts/dev_image_id.py and passed in via MRMAP_FRONTEND_IMAGE_FP
#     (set by docker-compose.prebuilt-frontend.yml). The host fingerprint also
#     covers the Dockerfile and this script, so it is the canonical identity
#     of the whole dependency environment.
#
# The volume marker (node_modules/.mrmap-deps-fp) records BOTH values on one
# space-separated line, so a volume is reused without any install only when
# neither the canonical image nor the installed tree changed since the last
# seed/install.
# A one-field marker written by the #963 bootstrap is still understood: it
# counts as a match only while no canonical fp is exported (plain :main flow).
# When no dependency tree is baked into the image (plain node:26-alpine, the
# non-prebuilt path) the script does nothing.
set -eu

APP_DIR=/opt/mrmap/frontend
DEPS_DIR=/opt/frontend-deps
NM_DIR="$APP_DIR/node_modules"
MARKER="$NM_DIR/.mrmap-deps-fp"

if [ ! -d "$DEPS_DIR/node_modules" ]; then
    exec "$@"
fi

image_fp=$(cat "$DEPS_DIR/.mrmap-deps-fp" 2>/dev/null || echo none)
current_fp=$({ cat "$APP_DIR/package.json" "$APP_DIR/package-lock.json"; node -v; npm -v; } | sha256sum | cut -d ' ' -f1 | cut -c1-12)
canonical_fp=${MRMAP_FRONTEND_IMAGE_FP:-$current_fp}

recorded=$(cat "$MARKER" 2>/dev/null || true)
# split the marker into its canonical and deps fields (single-space separated);
# a legacy one-field marker has the deps fp in both roles. `read` (not
# `set --`) so the container command in "$@" stays intact.
m_canon=""
m_deps=""
IFS=' ' read -r m_canon m_deps <<EOF
$recorded
EOF
if [ -n "$m_canon" ] && [ -z "$m_deps" ]; then
    m_deps="$m_canon"
fi

if [ -n "$m_canon" ] && [ "$m_canon" = "$canonical_fp" ] && [ "$m_deps" = "$current_fp" ]; then
    echo "frontend-deps: node_modules volume is up to date (fp $current_fp, image $canonical_fp)" >&2
else
    if [ "$image_fp" = "$current_fp" ]; then
        echo "frontend-deps: seeding node_modules from image (fp $current_fp, image $canonical_fp)" >&2
        mkdir -p "$NM_DIR"
        find "$NM_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
        cp -a "$DEPS_DIR/node_modules/." "$NM_DIR/"
    else
        echo "frontend-deps: mounted lockfile ($current_fp) differs from image ($image_fp) - running npm ci" >&2
        ( cd "$APP_DIR" && npm ci --no-audit --no-fund )
    fi
    echo "$canonical_fp $current_fp" > "$MARKER"
fi

exec "$@"
