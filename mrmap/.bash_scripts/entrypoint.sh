#!/bin/bash

/opt/mrmap/.bash_scripts/wait_db.sh


# run mrmap setup command. It will handle everthing we need to pre setup the system.
python manage.py setup

cp -rf /tmp/mrmap/static/* /var/www/mrmap/static

# run collectstatic
python manage.py collectstatic --noinput


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

Preconfiguration is done. MrMap is ready...
'

exec "$@"