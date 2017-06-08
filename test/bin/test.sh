#!/usr/bin/env bash

set -e
unset CDPATH
cd "$( dirname "${BASH_SOURCE[0]}" )/../.."


function usage() {
cat >&2 <<EOF
Run scitran-reaper tests

Usage:
    $0 [OPTION...]

Options:
    -L, --no-lint           Skip linting
    -U, --no-unit           Skip unit tests
    -h, --help              Print this help and exit
    --core-url value        URL for Scitran REST API
    --core-secret value     Auth secret for Scitran REST API
    --dicom-scp-host value  hostname/ip for DICOM server
    --dicom-scp-port value  Listening Port for DICOM server
    --dicom-scp-aet value   AE Title for DICOM server
    --orthanc value         URL to Orthanc REST API
    --testdata value        Path to testdata
    -- PYTEST_ARGS          Arguments passed to py.test


EOF
}

function main() {


    local RUN_LINT=true
    local RUN_UNIT=true
    local RUN_INTEG=true
    local PYTEST_ARGS=
    local TESTDATA_DIR=

    while [[ "$#" > 0 ]]; do
        case "$1" in
            -L|--no-lint)     RUN_LINT=false;           ;;
            -U|--no-unit)     RUN_UNIT=false;           ;;
            --core-url)
              CORE_URL="$2"
              shift;;
            --core-secret)
              CORE_SECRET="$2"
              shift;;
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
            --)               PYTEST_ARGS="${@:2}"; echo "$PYTEST_ARGS";     break;;
            -h|--help)        usage;                    exit 0;;
            *) >&2 echo "Invalid argument: $1"; usage;  exit 1;;
        esac
        shift
    done

  # install dependencies
  pip install -r test/requirements.txt
  pip freeze

  if ${RUN_LINT} ; then
    ./test/bin/lint.sh
  fi

  if ${RUN_UNIT} ; then
    >&2 echo
    >&2 echo "Running unit tests ..."
    #TODO: add unit tests
  fi

  # Validate input dependencies

  # Dicom_SCP required TESTDATA_DIR


  # Orthanc requires DICOM_SCP
  if [ ${ORTHANC_REST_URL} ] ; then
    if [ -z ${DICOM_SCP_HOST} ] || [ -z ${DICOM_SCP_PORT} ] || [ -z ${DICOM_SCP_AET} ] || [ -z ${CORE_URL} ] || [ -z ${CORE_SECRET} ] ; then
      >&2 echo "ERROR: orthanc testing requires ..."
    fi
  fi

  # TODO: check testdata provided if DICOM stuff provided

  if [ ${DICOM_SCP_HOST} ] && [ ${DICOM_SCP_PORT} ] && [ ${DICOM_SCP_AET} ] && [ ${TESTDATA_DIR} ] ; then
    >&2 echo
    >&2 echo "INFO: Loading test data into DICOM SCP"
    storescu -v --scan-directories -aec "${DICOM_SCP_AET}" "${DICOM_SCP_HOST}" "${DICOM_SCP_PORT}"  $(find $TESTDATA_DIR -type d -name dicom | tail -n 1)

    >&2 echo
    >&2 echo "INFO: Test DICOM Sniper"
    dicom_sniper -y --secret "${CORE_SECRET}" -k StudyID "" "${DICOM_SCP_HOST}" "${DICOM_SCP_PORT}" 5104 REAPER "${DICOM_SCP_AET}" "${CORE_URL}"

    >&2 echo
    >&2 echo "INFO: Test DICOM Reaper"
    dicom_reaper -o -s 1 --secret "${CORE_SECRET}" $(mktemp) "${DICOM_SCP_HOST}" "${DICOM_SCP_PORT}" 5104 REAPER "${DICOM_SCP_AET}" "${CORE_URL}"

    if [ ${ORTHANC_REST_URL} ] ; then
      >&2 echo
      >&2 echo "INFO: Test Orthanc DICOM Reaper"
      orthanc_reaper -o -s 1 --secret "${CORE_SECRET}" $(mktemp) "${DICOM_SCP_HOST}" "${DICOM_SCP_PORT}" 5104 REAPER "${DICOM_SCP_AET}" "${ORTHANC_REST_URL}" "${CORE_URL}"
    fi
  fi

  if [ ${TESTDATA_DIR} ] && [ ${CORE_URL} ] && [ ${CORE_SECRET} ] ; then
    # Test Folder Sniper
    folder_sniper -y --secret "${CORE_SECRET}" "${TESTDATA_DIR}" "${CORE_URL}"
  fi


}


main "$@"
