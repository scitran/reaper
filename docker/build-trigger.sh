#!/usr/bin/env bash

# Triggers an auto-build (on dockerhub) for the given source control reference.
#
# Example usage: ./build-trigger Tag 1.0.0 https://registry.hub.docker.com/u/scitran/reaper/trigger/11111111-2222-3333-4444-abcdefabcdef/

SOURCE_CONTROL_REF_TYPE="${1}"
SOURCE_CONTROL_REF_NAME="${2}"
TRIGGER_URL="${3}"

if [ -z "${SOURCE_CONTROL_REF_TYPE}" ] ; then
  >&2 echo "INFO: Source control reference type provided, skipping build trigger."
  exit 0
fi

if [ -z "${SOURCE_CONTROL_REF_NAME}" ] ; then
  >&2 echo "INFO: Source control tag name not provided, skipping build trigger."
  exit 0
fi

TRIGGER_PAYLOAD="{\"source_type\": \"${SOURCE_CONTROL_REF_TYPE}\", \"source_name\": \"${SOURCE_CONTROL_REF_NAME}\"}"
curl -H "Content-Type: application/json" --data "${TRIGGER_PAYLOAD}" -X POST "${TRIGGER_URL}"
