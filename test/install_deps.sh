#!/usr/bin/env bash

set -u

if [ ! -f $DCMTK_VERSION/config/config.status ]; then
    curl http://dicom.offis.de/download/dcmtk/snapshot/old/$DCMTK_VERSION.tar.gz | tar xz
    cd $DCMTK_VERSION
    curl https://raw.githubusercontent.com/scitran/reaper/master/movescu.cc.patch | patch --strip 1
    ./configure --prefix=$VIRTUAL_ENV
    make all
else
    cd $DCMTK_VERSION
fi

make install
