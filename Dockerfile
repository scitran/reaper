#
# Image used for execution of reaper functions.
#
# Example usage is in README.md
#

FROM ubuntu:16.04


# Install pre-requisites
RUN apt-get update \
  && apt-get install -y \
    build-essential \
    ca-certificates curl \
    libatlas3-base \
    numactl \
    python-dev \
    python-pip \
    libffi-dev \
    libssl-dev \
    git \
  && rm -rf /var/lib/apt/lists/* \
  && pip install -U pip


COPY movescu.cc.patch /tmp/
RUN cd /tmp \
  && curl http://dicom.offis.de/download/dcmtk/snapshot/old/dcmtk-3.6.1_20150924.tar.gz | tar xz \
  && cd dcmtk-* \
  && cat /tmp/movescu.cc.patch | patch --strip 1 \
  && ./configure \
  && make all \
  && make install \
  && cd /tmp \
  && rm -rf dcmtk-* \
  && rm movescu.cc.patch


COPY bin /var/scitran/code/reaper/bin/
COPY reaper /var/scitran/code/reaper/reaper/
COPY LICENSE setup.py /var/scitran/code/reaper/

RUN locale-gen en_US.UTF-8
ENV LANG='en_US.UTF-8' LANGUAGE='en_US:en' LC_ALL='en_US.UTF-8'
RUN pip install --upgrade -e /var/scitran/code/reaper


# Inject build information into image
ARG BRANCH_LABEL=NULL
ARG COMMIT_HASH=0
LABEL io.github.scitran.branch="${BRANCH_LABEL}" io.github.scitran.commit-hash="${COMMIT_HASH}"
