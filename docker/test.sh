#!/usr/bin/env bash

set -ex

unset CDPATH
cd "$( dirname "${BASH_SOURCE[0]}" )/.."

function usage() {
cat >&2 <<EOF
Run scitran-reaper tests

Usage:
    $0 [OPTION...] [-- PYTEST_ARGS...]

PYTEST_ARGS:        Arguments passed to py.test

Options:
    -B, --no-build      Skip Docker Builds

EOF
}

function main() {
  local DOCKER_BUILD=true

  while [[ "$#" > 0 ]]; do
      case "$1" in
          -B|--no-build)    DOCKER_BUILD=false;           ;;
          -h|--help)        usage;                    exit 0;;
          *) echo "Invalid argument: $1" >&2; usage;  exit 1;;
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
  docker run -d --rm --name orthanc-test --network reaper-test orthanc-test


  # scitran-core
  docker run -d --rm --name scitran-core-mongo --network reaper-test mongo
  docker run -d --rm --name scitran-core \
    --network reaper-test \
    -e "SCITRAN_PERSISTENT_DB_URI=mongodb://scitran-core-mongo:27017/scitran" \
    -e "SCITRAN_PERSISTENT_DB_LOG_URI=mongodb://scitran-core-mongo:27017/logs" \
    -e "SCITRAN_CORE_DRONE_SECRET=secret" \
    scitran/core


  # Fetch test data
  TESTDATA_DIR="./testdata"
  mkdir -p $TESTDATA_DIR
  if [ ! "$(ls -A $TESTDATA_DIR)" ]; then
      curl -L https://github.com/scitran/testdata/archive/master.tar.gz | tar xz -C "$TESTDATA_DIR" --strip-components 1
  fi


  docker run -it \
    --rm \
    --name reaper-test \
    --network reaper-test \
    -v "$(pwd)/testdata:/testdata" \
    -v "$(pwd)/bin:/src/reaper/bin" \
    -v "$(pwd)/reaper:/src/reaper/reaper" \
    -v "$(pwd)/test:/src/reaper/test" \
    reaper-test \
      /src/reaper/test/bin/test.sh \
      --testdata /testdata \
      --core http://scitran-core:8080 secret \
      --dicom-scp-host orthanc-test
      --dicom-scp-port 4242
      --dicom-scp-aet ORTHANC
      --orthanc http://orthanc-test:8042
}

clean_up () {(
  set +e

  # Spin down dependencies
  docker logs scitran-core-mongo
  docker stop scitran-core-mongo

  docker logs scitran-core
  docker stop scitran-core

  docker logs orthanc-test
  docker stop orthanc-test

  docker network rm reaper-test
)}
trap clean_up EXIT

main "$@"
