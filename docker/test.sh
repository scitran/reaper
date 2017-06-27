#!/usr/bin/env bash

set -e

unset CDPATH
cd "$( dirname "${BASH_SOURCE[0]}" )/.."

function usage() {
cat >&2 <<EOF
Run scitran-reaper tests

Usage:
    $0 [OPTION...] [-- TEST_ARGS...]

Options:
    -B, --no-build      Skip Docker Builds
    -h, --help          Print this help and exit
    --testdata path     Path to testdata.
    -- TEST_ARGS        Arguments passed to test/bin/test.sh

EOF
}

function main() {
  local DOCKER_BUILD=true
  local TEST_ARGS=
  local TESTDATA_DIR=

  while [[ "$#" > 0 ]]; do
      case "$1" in
          -B|--no-build)    DOCKER_BUILD=false;              ;;
          -h|--help)        usage;                    exit 0 ;;
          --testdata)
            TESTDATA_DIR="$2";
            if [ ! "$(ls -A $TESTDATA_DIR)" ] ; then
              >&2 echo "ERROR: --testdata must exist and not be empty."
              exit 1
            fi
            shift
            ;;
          --)               TEST_ARGS="${@:2}";     break;;
          *) echo "Invalid argument: $1" >&2; usage;  exit 1 ;;
      esac
      shift
  done

  if $DOCKER_BUILD ; then
    # build this repo
    docker build -t reaper-test .

    # build dependencies
    docker build -t orthanc-test -f docker/Dockerfile-orthanc docker/
  fi

  #Spin up dependencies
  docker network create reaper-test


  # Orthanc
  #   calledAE = ORTHANC 4242
  #   REST port = 8042
  docker run -d --name orthanc-test --network reaper-test orthanc-test


  # scitran-core
  docker run -d --name scitran-core-mongo --network reaper-test mongo
  docker run -d --name scitran-core \
    --network reaper-test \
    -e "SCITRAN_PERSISTENT_DB_URI=mongodb://scitran-core-mongo:27017/scitran" \
    -e "SCITRAN_PERSISTENT_DB_LOG_URI=mongodb://scitran-core-mongo:27017/logs" \
    -e "SCITRAN_CORE_DRONE_SECRET=secret" \
    scitran/core


  # Fetch test data
  if [ -z ${TESTDATA_DIR} ]; then
    TESTDATA_DIR="./testdata"
    mkdir -p $TESTDATA_DIR
    if [ ! "$(ls -A $TESTDATA_DIR)" ]; then
        curl -L https://github.com/scitran/testdata/archive/master.tar.gz | tar xz -C "$TESTDATA_DIR" --strip-components 1
    fi
  fi

  # Make sure testdata path is absolute. Could be either absolute or relative.
  TESTDATA_DIR="$(cd "$(dirname "$TESTDATA_DIR")" && pwd)/$(basename "$TESTDATA_DIR")"

  set +e
  docker run -it \
    --rm \
    --name reaper-test \
    --network reaper-test \
    -v "$TESTDATA_DIR:/testdata" \
    -v "$(pwd)/bin:/src/reaper/bin" \
    -v "$(pwd)/reaper:/src/reaper/reaper" \
    -v "$(pwd)/tests:/src/reaper/tests" \
    reaper-test \
      /src/reaper/tests/bin/test.sh \
      --testdata /testdata \
      --core-url http://scitran-core:8080 \
      --core-secret secret \
      --dicom-scp-host orthanc-test \
      --dicom-scp-port 4242 \
      --dicom-scp-aet ORTHANC \
      --orthanc http://orthanc-test:8042 \
      $TEST_ARGS

  TEST_RESULT_CODE=$?
  >&2 echo
  >&2 echo "INFO: Test return code = $TEST_RESULT_CODE"
  if [ "${TEST_RESULT_CODE}" != "0" ] ; then
    >&2 echo "INFO: Printing container logs..."
    docker logs scitran-core-mongo
    docker logs scitran-core
    docker logs orthanc-test
    >&2 echo
    >&2 echo "ERROR: Test return code = $TEST_RESULT_CODE. Container logs printed above."
  fi
}

clean_up () {(
  set +e
  # Spin down dependencies
  docker rm -f -v scitran-core-mongo
  docker rm -f -v scitran-core
  docker rm -f -v orthanc-test
  docker network rm reaper-test
)}
trap clean_up EXIT

main "$@"
