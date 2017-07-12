#!/usr/bin/env bash

set -eu

unset CDPATH
cd "$( dirname "${BASH_SOURCE[0]}" )/.."

echo "Running pylint ..."
pylint --jobs=2 --reports=no --disable=R1705 reaper

echo

echo "Running pep8 ..."
pep8 --max-line-length=150 --ignore=E402 reaper
