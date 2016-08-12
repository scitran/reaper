#!/usr/bin/env bash

set -u

# DCMTK
(
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
)

# Orthanc
(
if [ ! -f "$ORTHANC_VERSION/Orthanc" ]; then
  curl -L "http://www.orthanc-server.com/downloads/get.php?path=/orthanc/$ORTHANC_VERSION.tar.gz" | tar xz
  cd "$ORTHANC_VERSION"
  cmake -DCMAKE_INSTALL_PREFIX=$VIRTUAL_ENV -DSTATIC_BUILD=ON -DCMAKE_BUILD_TYPE=Release
  make
else
  cd "$ORTHANC_VERSION"
fi

make install
)
