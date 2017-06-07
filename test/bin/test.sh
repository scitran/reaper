#!/usr/bin/env bash

set -e

function usage() {
cat >&2 <<EOF
Run scitran-reaper tests

Usage:
    $0 [OPTION...] [-- PYTEST_ARGS...]

PYTEST_ARGS:        Arguments passed to py.test

Options:
    -L, --no-lint       Skip linting
    -U, --no-unit       Skip unit tests
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
    local TESTDATA_DIR=

    while [[ "$#" > 0 ]]; do
        case "$1" in
            -L|--no-lint)     RUN_LINT=false;           ;;
            -U|--no-unit)     RUN_UNIT=false;           ;;
            --core)
              CORE_URL="$2"
              CORE_SECRET="$3"
              shift 2;;
            --dicom-scp-host)
              DICOM_SCP_HOST="$2"
              shift;;
            --dicom-scp-port)
              DICOM_SCP_PORT="$2"
              shift;;
            --dicom-scp-aet)
              DICOM_SCP_AET="$2"
              shift;;
            --orthanc)
              ORTHANC_REST_URL="$2"
              shift;;
            --testdata)
              TESTDATA_DIR="$2"
              shift;;
            --)               PYTEST_ARGS="${@:2}";     break;;
            -h|--help)        usage;                    exit 0;;
            *) echo "Invalid argument: $1" >&2; usage;  exit 1;;
        esac
        shift
    done

  if ${RUN_LINT} ; then
    echo
    echo "Running pylint ..."
    pylint --jobs=2 --reports=no --disable=R1705 reaper

    echo
    echo "Running pep8 ..."
    pep8 --max-line-length=150 --ignore=E402 reaper
  fi

  if ${RUN_UNIT} ; then
    echo
    echo "Running unit tests ..."
    #TODO: add unit tests
  fi

    # TODO: Make this conditional for tests that require it.
    storescu -v --scan-directories -aec "${DICOM_SCP_AET}" "${DICOM_SCP_HOST}" "${DICOM_SCP_PORT}"  $(find $TESTDATA_DIR -type d -name dicom | tail -n 1)

    # Test DICOM Sniper
    dicom_sniper -y --secret "${CORE_SECRET}" -k StudyID "" "${DICOM_SCP_HOST}" "${DICOM_SCP_PORT}" 5104 REAPER "${DICOM_SCP_AET}" "${CORE_URL}"


    # Test DICOM Reaper
    dicom_reaper -o -s 1 --secret "${CORE_SECRET}" $(mktemp) "${DICOM_SCP_HOST}" "${DICOM_SCP_PORT}" 5104 REAPER "${DICOM_SCP_AET}" "${CORE_URL}"


    # Test Folder Sniper
    folder_sniper -y --secret "${CORE_SECRET}" "${TESTDATA_DIR}" "${CORE_URL}"


    orthanc_reaper -o -s 1 --secret "${CORE_SECRET}" $(mktemp) "${DICOM_SCP_HOST}" "${DICOM_SCP_PORT}" 5104 REAPER "${DICOM_SCP_AET}" "${ORTHANC_REST_URL}" "${CORE_URL}"


  sleep 10000
}


main "$@"
