### Installation

```
(
PYTHON_VERSION=2.7.11
cd /tmp
curl https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz | tar xz
cd Python-$PYTHON_VERSION
./configure --with-ensurepip
make
sudo make install
sudo /usr/local/bin/pip install -U pip setuptools wheel ipython virtualenv
)

virtualenv --prompt "(reaper)" reaperenv
source reaperenv/bin/activate

(
cd /tmp
curl http://dicom.offis.de/download/dcmtk/snapshot/old/dcmtk-3.6.1_20150924.tar.gz | tar xz
cd dcmtk-*
./configure --prefix=$VIRTUAL_ENV
make all
make install
)

git clone https://github.com/scitran/reaper.git && cd reaper
pip install -r requirements.txt -r requirements_dicom.txt
```

### Reaping

```
PYTHONPATH=. bin/pfile_reaper.py <path>
PYTHONPATH=. bin/dicom_reaper.py <host> <port> <return port> reaper <scanner AET>
PYTHONPATH=. bin/dicom_file_reaper.py <path>
PYTHONPATH=. bin/meeg_file_reaper.py <path>

```


### Debugging

```
findscu --verbose -S -aet reaper -aec <scanner AET> -k QueryRetrieveLevel="STUDY" -k StudyDate="" <host> <port>
findscu --verbose -S -aet reaper -aec <scanner AET> -k QueryRetrieveLevel="SERIES" -k StudyDate="" <host> <port>
```


### Development

```
./reaper/meeg_file_reaper.py -s 1 -i -u https://localhost:8443/api/reaper?secret=change-me <path>
```
