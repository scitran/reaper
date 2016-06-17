#!/usr/bin/env bash

set -euv

unset CDPATH
cd "$( dirname "${BASH_SOURCE[0]}" )/.."


# Set up exit and error trap to shutdown dependencies
shutdown() {
    echo 'Exit signal trapped'
    kill $RECEIVER_PID
    wait
}
trap "shutdown" EXIT ERR


# Launch DICOM test server
#dcmtk &
#DCMTK_PID=$!


# Launch dummy upload receiver
python -m httpbin.core --port 8000 &
RECEIVER_PID=$!


# Fetch test data
TEMPDIR=$(mktemp -d)
curl -L https://github.com/scitran/testdata/archive/master.tar.gz | tar xz -C $TEMPDIR --strip-components 1


# Test DICOM Sniper


# Test DICOM Reaper


# Test Folder Sniper
folder_uploader -y $TEMPDIR http://localhost:8000/post


# Cleanup
rm -r $TEMPDIR
