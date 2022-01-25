#!/bin/bash

export $( grep -v '^#' ./docs/.docs.env | xargs )
BRANCH=$( git branch --show-current )


MRMAP_MEDIA_DIR=./tmp sphinx-multiversion docs/source docs/build/html -b linkcheck -D smv_branch_whitelist=r'^${BRANCH}.*$'
MRMAP_MEDIA_DIR=./tmp sphinx-multiversion docs/source docs/build/html -b html -E -D smv_branch_whitelist=r'^${BRANCH}.*$'

exec "$@"