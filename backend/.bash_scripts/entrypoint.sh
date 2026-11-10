#!/bin/sh
RED='\033[0;31m'
GREEN='\033[0;32m'
NOCOLOR='\033[0m'
if ! /opt/mrmap/.bash_scripts/wait_db.sh; then
  printf "${RED}database never started accepting connections - giving up${NOCOLOR}\n"
  exit 1
fi

if [[ $(hostname -s) = *backend* ]]; then 
  # migrate is the true readiness test (#901): the pg_isready probe above can
  # pass and the server can still refuse the next connection a moment later,
  # so retry a bounded number of times before letting the container exit.
  MIGRATE_ATTEMPTS="${MIGRATE_ATTEMPTS:-5}"
  MIGRATE_RETRY_DELAY="${MIGRATE_RETRY_DELAY:-10}"
  attempt=1
  while true; do
    echo "django migrate (attempt $attempt/$MIGRATE_ATTEMPTS)"
    if python manage.py migrate; then
      printf "${GREEN}database migrations applied${NOCOLOR}\n"
      break
    fi
    if [ "$attempt" -ge "$MIGRATE_ATTEMPTS" ]; then
      printf "${RED}failed to migrate database after $attempt attempts${NOCOLOR}\n"
      exit 1
    fi
    printf "${RED}migrate failed, retrying in ${MIGRATE_RETRY_DELAY}s${NOCOLOR}\n"
    attempt=$((attempt + 1))
    sleep "$MIGRATE_RETRY_DELAY"
  done
fi

echo '
MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM
MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMNmhyyyyhhhddmMMMMMMMMMMMMM
MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMNmhso/:.`./`.oshdddhs++symMMMMMMMMM
MMMMMMMMMMMMMMMMMMMMMMMMMMNmdyo+:-:/-.``````.sdmdhysoosmh++++oyNMMMMMM
MMMMMMMMMMMMMMMMMMMNddyso++/```````````-....sNo++++++++oMo+++++oyMMMMM
MMMMMMMMMMMMMMMmy+::++++++++.````````:+o++++dd+++++++++yNo+++++++oNMMM
MMMMMMMMMMMMNho+++++++++++++.`.-/+sydNMMo+++sNyooosyhdmNs+++++++-.:mMM
MMMMMMMMMMms+++::+++++++++ommNMMMNmddhy/+++++ohmmddhyhshyo+++++++.`:MM
MMMMMMMMMo//++/``.``-+++++/yss+-.```://:+++++++:++++++syyyhso+++/.``sM
MMMMMMMm/:::://:--.``-+++-```````./-.+++ooo:+hmmddho++++syyos++-``-..M
MMMMMMN+--:/:/+/:/+/``.:/.```````--/+odNMMMNMMMMMMMMdo++++::/+++``.-.d
MMMMMMy/++-:+++/.:/:.``````````````-yMMMMMMMMMMMMMMMMNs/+:```.oo`-+-.y
MMMMMdos++++++..`/+++/:.```````````yMMMMMMMMMMMMMMMMMMMd+:.``.sM/-:.-s
MMMMMhyyo+++++---.++++-:.`````````-MMMMMMMMMddMMMMMMMMMMMds+ohMM:..``y
MMMMMyyys++++++++++++/-```````````dMMMMMMMMNo+ymMMMMMMMMMMMMMMm/````-d
MMMMMyyyyo++++++++++/`````+-`````oMMMMMMMMNo++++shdNMMMMMMNho:``````+M
MMMMMs+syyo+++++++++:`````Nh.``:yMMMMMMMMh++++++++.`.---.```` `````.NM
MMMMMy//+yyo+++++++/``````+MMMMMMMMMMMms.`./+++++++`/-````    ````.dMM
MMMMMN///+yys+++/.``--..```-ohdmmdhs/-``````-+++++:`/-`  `:so ```-mMMM
MMMMMMs/////oo+++.-:.``--::--````          `.///++:`  `:oyyyy` `sMMMMM
MMMMMMN+////////:---:.-++++++++++- +soo+//::--..``  -oyyyyyyy- mMMMMMM
MMMMMMMN+///////:-````.++++++++++- :yyyyyyyyyyyyyyyyyyyyyyyyy+ sMMMMMM
MMMMMMMMNo/////////:.``/+++++++++: `yyyyyyyyyyyyyyyyyyyyyyyyyy -MMMMMM
MMMMMMMMMMd+//////////:--//+++++-`  oyyyyyyyyyyyyy+-........--` mMMMMM
MMMMMMMMMMMMds/////////////yysss:-- :yyyyyyyyyy+- .odddddddhhhhhmMMMMM
MMMNNmMMNmo/:sMmhso++/////+yhhddhdN-`yyyyyyy+. -omMMMMMMMMMMMMMMMMMMMM
Ndy...+mhs.-.:NMdmNhydMMMMMMMMMMMMMo oyys/. -smMMMMMMMMMMMMMMMMMMMMMMM
mhh:.+./yo.o-.hh::-:+yMMMMMMMMMMMMMm -/. :yNMMMMMMMMMMMMMMMMMMMMMMMMMM
Mhh+.os-::.y/.ohs.-dmMMMMMMMMMMMMMMM.`:yNMMMMNds+/::+hmMMMMMMMMMMMMMMM
Mdhy./hy/./hs.:hyo.mMMMMNddMMMMMMNmMmNMMMMMmh-..osss+--sNMMMMMMMMMMMMM
Mmhh--dhhydhh-.yhy/odmMmy//mMNdo/--+mMMMMMdhh+..hdhhhs..hMMMMMMMMMMMMM
MNhh+-hNmmNhhsshs/:..+NNmNMNhhs..+..:dMMMMmhhy..+MNhy/.:mMMMMMMMMMMMMM
MMdhhy/-:.-smhhh/....-hMMMMmhy+..yy:.-sNMMMhhh+..ss/-./yNMMMMMMMMMMMMM
MMmhhh-..-..ydhy:.-/..oMMMMdhh:.-hhy/..+NMMdhhy...:+oymMMMMMMMMMMMMMMM
MMNhhho..+/..ohh-.+s../NMMNhhy-./ho/-...:dMmhhy:.-ydNMMMMMMMMMMMMMMMMM
MMMdhhy..:ho-./s..sh-.-dMMdhho....-/oyy:.-omhhh+../NMMMMMMMMMMMMMMMMMM
MMMmhhh/.-hhs-...-hh+..sNMhhh/..:yhdhhhh/../hhhy..-dMMMMMMMMMMMMMMMMMM
MMMMhhho..shyy+../hhy..-mmhhy...+mMMNdhhyo-:dhhy+osdMMMMMMMMMMMMMMMMMM
MMMMdhhy..+dhhhsyhhhh:..shhho---hMMMMMmhhhhNMhhhhhmMMMMMMMMMMMMMMMMMMM
MMMMmhhh/.-dNhhdmMhhh+--ohhhhhyhNMMMMMMNNMMMMMNMMMMMMMMMMMMMMMMMMMMMMM
MMMMNhhho--yMMMMMMmhhhhhmmmdddmMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM
MMMMMdhhhhhhMMMMMMNmdmmNMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM
MMMMMNhhddmMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM

MrMap is ready. Application server is starting now.
'

exec "$@"