#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail


export REAPER_IMAGE=scitran-reaper:run-tests
export REAPER_CONTAINER=scitran-reaper-test


function usage() {
cat >&2 <<EOF
Run scitran-reaper tests using docker

Usage:
    $0 [-b] [-- RUNTEST_ARGS... [-- PYTEST_ARGS...]]

Options:
    -b, --build-image   Rebuild scitran-reaper image
    -h, --help          Print this help and exit

EOF
}


function main() {
    unset CDPATH
    cd "$( dirname "${BASH_SOURCE[0]}" )/../.."

    declare -x BUILD_IMAGE=false
    declare -x RUNTEST_ARGS=

    while [[ $# > 0 ]]; do
        case $1 in
            -b|--build-image)   BUILD_IMAGE=true;       shift;;
            --)                 RUNTEST_ARGS="${@:2}";  break;;
            -h|--help)          usage;                  exit 0;;
            *) echo "Invalid argument: $1" >&2; usage;  exit 1;;
        esac
    done

    local EXISTING_IMAGE="$( docker image ls --quiet --filter reference=$REAPER_IMAGE )"
    if [[ "$EXISTING_IMAGE" == "" || $BUILD_IMAGE == true ]]; then
        echo "Building $REAPER_IMAGE"
        docker build --tag $REAPER_IMAGE .
    fi


    trap clean_up EXIT

    (
        # Execute tests
        docker container run \
            --name $REAPER_CONTAINER \
            --volume $( pwd ):/src/reaper/reaper \
            --env DCMTK_VERSION=dcmtk-3.6.1_20150924 \
            --env DCMTK_DB_DIR=/src/reaper/reaper/test/data/dcmtk_dicom_db \
            --env DOWNLOAD_DIR=/src/reaper/reaper/test/deps \
            --env INSTALL_DIR=/src/reaper/reaper/test/deps \
            --env TESTDATA_DIR=/src/reaper/reaper/test/data/testdata \
            --env ORTHANC_VERSION=Orthanc-1.1.0 \
            --workdir /src/reaper/reaper \
            --entrypoint bash \
            --interactive \
            --tty \
            $REAPER_IMAGE \
            -c "./test/bin/setup-tests.sh && ./test/bin/run-tests.sh $RUNTEST_ARGS"
    )
}


function clean_up() {
    docker container rm --volumes --force $REAPER_CONTAINER
}


main "$@"
