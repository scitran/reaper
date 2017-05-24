#!/usr/bin/env bash
set -o errexit
set -o nounset
set -o pipefail


export DOWNLOAD_DIR=${DOWNLOAD_DIR:-.}
export INSTALL_DIR=${INSTALL_DIR:-$VIRTUAL_ENV}
export DCMTK_DB_DIR=${DCMTK_DB_DIR:-dcmtk_dicom_db}
export TESTDATA_DIR=${TESTDATA_DIR:-testdata}

export PATH=$INSTALL_DIR/sbin:$PATH


function usage() {
cat >&2 <<EOF
Run scitran-reaper tests

Usage:
    $0 [OPTION...] [-- PYTEST_ARGS...]

PYTEST_ARGS:        Arguments passed to py.test

Options:
    -L, --no-lint       Skip linting
    -U, --no-unit       Skip unit tests
    -I, --no-integ      Skip integration tests
    -h, --help          Print this help and exit

EOF
}


function main() {
    unset CDPATH
    cd "$( dirname "${BASH_SOURCE[0]}" )/../.."

    local RUN_LINT=true
    local RUN_UNIT=true
    local RUN_INTEG=true
    local PYTEST_ARGS=

    while [[ $# > 0 ]]; do
        case $1 in
            -L|--no-lint)     RUN_LINT=false;           shift;;
            -U|--no-unit)     RUN_UNIT=false;           shift;;
            -I|--no-integ)    RUN_INTEG=false;          shift;;
            --)               PYTEST_ARGS="${@:2}";     break;;
            -h|--help)        usage;                    exit 0;;
            *) echo "Invalid argument: $1" >&2; usage;  exit 1;;
        esac
    done

    if [[ $RUN_LINT == true ]]; then
        echo -e "\nRunning pylint ..."
        pylint --jobs=2 --reports=no --disable=R1705 reaper

        echo -e "\nRunning pep8 ..."
        pep8 --max-line-length=150 --ignore=E402 reaper
    fi

    if [[ $RUN_UNIT == true ]]; then
        echo -e "\nRunning unit tests ..."
        rm -rf .coverage test/unit_tests/__pycache__
        py.test --cov=reaper test/unit_tests $PYTEST_ARGS || [[ $? == 5 ]]
    fi

    if [[ $RUN_INTEG == true ]]; then
        echo -e "\nRunning integration tests ..."

        mkdir -p $TESTDATA_DIR
        if [[ ! "$(ls -A $TESTDATA_DIR)" ]]; then
            echo -e "\nFetch test data ..."
            curl -L https://github.com/scitran/testdata/archive/master.tar.gz | tar xz -C $TESTDATA_DIR --strip-components 1
        fi

        if [[ ! -f $DCMTK_DB_DIR/index.dat ]]; then
            echo -e "\nIndex DICOM files ..."
            mkdir -p $DCMTK_DB_DIR
            find $TESTDATA_DIR -type f -exec dcmqridx $DCMTK_DB_DIR {} +
        fi

        # Trap to ensure all background jobs are killed
        trap "exit" INT TERM
        trap "kill 0" EXIT

        echo -e "\nConfigure and launch DICOM server ..."
        local DCMQRSCP_CONFIG_FILE=$(mktemp)
        cp test/integration_tests/dicom-server.conf $DCMQRSCP_CONFIG_FILE
        sed --in-place "s#\$DCMTK_DB_DIR#$DCMTK_DB_DIR#" $DCMQRSCP_CONFIG_FILE
        dcmqrscp -c $DCMQRSCP_CONFIG_FILE &

        echo -e "\nConfigure and launch Orthanc ..."
        local ORTHANC_CONFIG_FILE=$(mktemp)
        cp test/integration_tests/orthanc-config.json $ORTHANC_CONFIG_FILE
        Orthanc $ORTHANC_CONFIG_FILE &
        until $(curl --output /dev/null --silent --fail http://localhost:8042); do
            printf '.'
            sleep 1
        done
        storescu -v --scan-directories -aec ORTHANC localhost 4242 $(find $TESTDATA_DIR -type d -name dicom | tail -n 1)

        echo -e "\nLaunch dummy upload receiver ..."
        local API_PORT=${API_PORT:-"8027"}
        local API_HOST=${API_HOST:-"http://localhost:$API_PORT"}
        uwsgi --http :$API_PORT --wsgi-file test/integration_tests/upload_receiver.wsgi --master --die-on-term &

        # Test DICOM Sniper
        dicom_sniper -y --secret secret -k StudyID "" localhost 5104 3333 REAPER DCMQRSCP $API_HOST

        # Test DICOM Reaper
        dicom_reaper -o -s 1 --secret secret $(mktemp) localhost 5104 3333 REAPER DCMQRSCP $API_HOST

        # Test Folder Sniper
        folder_sniper -y --secret secret $TESTDATA_DIR $API_HOST

        # Test Orthanc DICOM Reaper
        orthanc_reaper -o -s 1 --secret secret $(mktemp) localhost 4242 3333 REAPER ORTHANC "http://localhost:8042" $API_HOST
    fi
}


main "$@"
