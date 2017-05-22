FROM python:2.7-alpine

RUN apk add --no-cache build-base curl

COPY dcmtk.patch /tmp
RUN cd /tmp \
 && curl http://support.dcmtk.org/redmine/attachments/download/87/dcmtk-3.6.1_20150924.tar.gz | tar xz \
 && cd dcmtk-* \
 && patch -p1 </tmp/dcmtk.patch \
 && ./configure \
 && make config-all ofstd-all oflog-all dcmdata-all dcmimgle-all dcmimage-all dcmjpeg-all dcmjpls-all dcmtls-all dcmnet-all \
 && make dcmdata-install dcmnet-install \
 && rm -rf /tmp/dcmtk*

COPY . /src/reaper

RUN pip install -e /src/reaper

CMD ["/bin/sh"]
