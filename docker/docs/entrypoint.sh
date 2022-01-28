#!/bin/bash
RED='\033[0;31m'
GREEN='\033[0;32m'
NOCOLOR='\033[0m'

export $( grep -v '^#' ./docs/.docs.env | xargs )

cd /opt/mrmap

BRANCH=$( git branch --show-current )
echo $BRANCH

if [ "$BRANCH" != "develop" ];
then
  MRMAP_MEDIA_DIR=./tmp sphinx-multiversion /opt/mrmap/docs/source /opt/mrmap/docs/build/html -b linkcheck -D smv_branch_whitelist=$BRANCH
else
  MRMAP_MEDIA_DIR=./tmp sphinx-multiversion /opt/mrmap/docs/source /opt/mrmap/docs/build/html -b linkcheck
fi

if [ $? != 0 ]; 
then
  exit 1
  printf "${RED}linkcheck failed${NOCOLOR}\n"
else
  printf "${GREEN}linkcheck successfully${NOCOLOR}\n"
fi


if [ "$BRANCH" != "develop" ];
then
  MRMAP_MEDIA_DIR=./tmp sphinx-multiversion /opt/mrmap/docs/source /opt/mrmap/docs/build/html -b html -E -D smv_branch_whitelist=$BRANCH
else
  MRMAP_MEDIA_DIR=./tmp sphinx-multiversion /opt/mrmap/docs/source /opt/mrmap/docs/build/html -b html -E
fi


if [ $? != 0 ]; 
then
  exit 1
  printf "${RED}building html failed${NOCOLOR}\n"
else
  printf "${GREEN}building html successfully${NOCOLOR}\n"
fi

exec "$@"