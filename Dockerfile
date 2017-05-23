FROM alpine as build

RUN apk add --no-cache build-base curl

WORKDIR dcmtk
RUN curl http://support.dcmtk.org/redmine/attachments/download/87/dcmtk-3.6.1_20150924.tar.gz | tar xz --strip-components 1

COPY dcmtk.patch .
RUN patch -p1 <dcmtk.patch

RUN ./configure
RUN make config-all ofstd-all oflog-all dcmdata-all dcmimgle-all dcmimage-all dcmjpeg-all dcmjpls-all dcmtls-all dcmnet-all
RUN make dcmdata-install dcmnet-install



FROM python:2.7-alpine

RUN apk add --no-cache libstdc++

COPY --from=build /usr/local/bin                /usr/local/bin
COPY --from=build /usr/local/etc/dcmtk          /usr/local/etc/dcmtk
COPY --from=build /usr/local/share/dcmtk        /usr/local/share/dcmtk
COPY --from=build /usr/local/share/doc/dcmtk    /usr/local/share/doc/dcmtk

COPY . /src/reaper

RUN pip install -e /src/reaper

CMD ["/bin/sh"]
