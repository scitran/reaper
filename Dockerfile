FROM alpine as build

RUN apk add --no-cache build-base git

RUN git clone git://git.dcmtk.org/dcmtk.git
WORKDIR dcmtk
RUN git checkout -qf 6c5329a82728bee2c7b6c7a05dbff192a2418d87

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
