#!/usr/bin/env bash

set -eu

unset CDPATH
cd "$( dirname "${BASH_SOURCE[0]}" )/.."

DCMTK_DB_DIR=${DCMTK_DB_DIR:-"./dcmtk_dicom_db"}
TESTDATA_DIR=${TESTDATA_DIR:-"./testdata"}


# Set up exit and error trap to shutdown dependencies
shutdown() {
    echo 'Exit signal trapped'
    kill $DCMQRSCP_PID $RECEIVER_PID
    wait
}
trap "shutdown" EXIT ERR


# Launch dummy upload receiver  # TODO not an ideal server as it returns the entire received payload
uwsgi --http :8000 --wsgi-file ./bin/dummy_upload_receiver.wsgi &
RECEIVER_PID=$!


# Fetch test data
mkdir -p $TESTDATA_DIR
if [ ! "$(ls -A $TESTDATA_DIR)" ]; then
    curl -L https://github.com/scitran/testdata/archive/master.tar.gz | tar xz -C $TESTDATA_DIR --strip-components 1
fi


# Populate DICOM test server
if [ ! -f $DCMTK_DB_DIR/index.dat ]; then
    mkdir -p $DCMTK_DB_DIR
    find $TESTDATA_DIR -type f -exec dcmqridx $DCMTK_DB_DIR {} +
fi


# Configure and launch DICOM test server
DCMQRSCP_CONFIG_FILE=$(mktemp)
cat << EOF > $DCMQRSCP_CONFIG_FILE
NetworkTCPPort  = 5104
MaxPDUSize      = 16384
MaxAssociations = 16

HostTable BEGIN
reaper          = (REAPER, localhost, 3333)
HostTable END

AETable BEGIN
DCMQRSCP        $DCMTK_DB_DIR RW (200, 1024mb) ANY
AETable END
EOF

dcmqrscp -c $DCMQRSCP_CONFIG_FILE &
DCMQRSCP_PID=$!


# Test DICOM Sniper
dicom_sniper -y -k StudyID "" localhost 5104 3333 REAPER DCMQRSCP http://localhost:8000


# Test DICOM Reaper
dicom_net_reaper -o -s 1 $(mktemp) localhost 5104 3333 REAPER DCMQRSCP -u http://localhost:8000


# Test Folder Sniper
folder_uploader -y $TESTDATA_DIR http://localhost:8000
