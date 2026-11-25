#!/bin/bash
RED='\033[0;31m'
GREEN='\033[0;32m'
NOCOLOR='\033[0m'

git config --global --add safe.directory /opt/mrmap

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


# -W makes every warning a build failure, which is what keeps the portal honest:
# a page that no toctree leads to, a reference to a label nobody defines and an
# include whose file is not there all warn, and each of them used to publish a
# quietly broken page (#1597). The strictness is here rather than only in CI
# because this is the entrypoint a contributor runs, and a warning a contributor
# can see is worth more than one a job reports days later.
if [ "$BRANCH" != "develop" ];
then
  MRMAP_MEDIA_DIR=./tmp sphinx-multiversion /opt/mrmap/docs/source /opt/mrmap/docs/build/html -b html -E -W --keep-going -D smv_branch_whitelist=$BRANCH
else
  MRMAP_MEDIA_DIR=./tmp sphinx-multiversion /opt/mrmap/docs/source /opt/mrmap/docs/build/html -b html -E -W --keep-going
fi


if [ $? != 0 ]; 
then
  exit 1
  printf "${RED}building html failed${NOCOLOR}\n"
else
  printf "${GREEN}building html successfully${NOCOLOR}\n"
fi

exec "$@"