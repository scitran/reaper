#!/usr/bin/env bash

set -eu

unset CDPATH
cd "$( dirname "${BASH_SOURCE[0]}" )/.."

DCMTK_DB_DIR=${DCMTK_DB_DIR:-"./dcmtk_dicom_db"}
TESTDATA_DIR=${TESTDATA_DIR:-"./testdata"}
ORTHANC_BUILD=${ORTHANC_BUILD:-"./Orthanc*Build"}

PORT=${PORT:-"8027"}
HOST=${HOST:-"http://localhost:$PORT"}


# Set up exit and error trap to shutdown dependencies
shutdown() {
    echo 'Exit signal trapped'
    kill $DCMQRSCP_PID $RECEIVER_PID
    wait
}
trap "shutdown" EXIT ERR


# Launch dummy upload receiver
uwsgi --http :$PORT --wsgi-file ./test/upload_receiver.wsgi --master --die-on-term &
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
#dicom_sniper -y -k StudyID "" localhost 5104 3333 REAPER DCMQRSCP $HOST


# Test DICOM Reaper
#dicom_reaper -o -s 1 $(mktemp) localhost 5104 3333 REAPER DCMQRSCP -u $HOST


# Test Folder Sniper
#folder_sniper -y $TESTDATA_DIR $HOST

# Test Orthanc DICOM Reaper
"${ORTHANC_BUILD}/Orthanc" &
ORTHANC_PID=$!
sleep 5

storescu -v --scan-directories -aec ORTHANC localhost 4242  $(find $TESTDATA_DIR -type d -name dicom | tail -n 1)
orthanc_reaper -o -s 1 $(mktemp) localhost 4242 3333 REAPER ORTHANC "http://localhost:8042" -u $HOST
