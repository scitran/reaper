#!/usr/bin/env bash

set -e

unset CDPATH
cd "$( dirname "${BASH_SOURCE[0]}" )/.."


#dcmtk &
#DCMTK_PID=$!
#
#upload_receiver.py &
#RECEIVER_PID=$!
#
#reap





## Set python path so scripts can work
#export PYTHONPATH=.
#
#
## Set up exit and error trap to shutdown mongod and paster
#trap "{
#    echo 'Exit signal trapped';
#    kill $DCMTK_PID $RECEIVER_PID; wait;
#    rm -f $TEMP_INI_FILE
#    deactivate
#}" EXIT ERR
#
#
## Wait for everything to come up
#sleep 2
#
#
## Wait for good or bad things to happen until exit or error trap catches
#wait
