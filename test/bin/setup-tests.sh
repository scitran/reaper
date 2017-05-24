#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail


export DOWNLOAD_DIR=${DOWNLOAD_DIR:-.}
export INSTALL_DIR=${INSTALL_DIR:-$VIRTUAL_ENV}


function main() {
    unset CDPATH
    cd "$( dirname "${BASH_SOURCE[0]}" )/../.."

    mkdir -p $DOWNLOAD_DIR

    # DCMTK
    (
        cd $DOWNLOAD_DIR
        if [[ ! -f $DCMTK_VERSION/config/config.status ]]; then
            curl http://dicom.offis.de/download/dcmtk/snapshot/old/$DCMTK_VERSION.tar.gz | tar xz
            cd $DCMTK_VERSION
            curl https://raw.githubusercontent.com/scitran/reaper/master/movescu.cc.patch | patch --strip 1
            ./configure --prefix=$INSTALL_DIR
            make all
            make install
        fi
    )

    # Orthanc
    (
        cd $DOWNLOAD_DIR
        if [[ ! -f $ORTHANC_VERSION/Orthanc ]]; then
            curl -L "http://www.orthanc-server.com/downloads/get.php?path=/orthanc/$ORTHANC_VERSION.tar.gz" | tar xz
            cd $ORTHANC_VERSION
            cmake -DCMAKE_INSTALL_PREFIX=$INSTALL_DIR -DSTATIC_BUILD=ON -DCMAKE_BUILD_TYPE=Release
            make
            make install
        fi
    )

    # Python test requirements
    pip install --editable .
    pip install --upgrade --requirement test/requirements.txt
}


main "$@"
