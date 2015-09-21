### Installation

```
cd /tmp
curl https://www.python.org/ftp/python/2.7.10/Python-2.7.10.tgz | tar xz
cd Python-2.7.10/
./configure --with-ensurepip
make
sudo make install
sudo /usr/local/bin/pip install -U pip setuptools wheel ipython virtualenv virtualenvwrapper

source /usr/local/bin/virtualenvwrapper.sh
mkvirtualenv reaper

cd /tmp
curl ftp://dicom.offis.de/pub/dicom/offis/software/dcmtk/snapshot/dcmtk-3.6.1_20150924.tar.gz | tar xz
cd dcmtk-*
./configure --prefix=$VIRTUAL_ENV
make all
make install

python setup.py install
```

### Reaping

```
./reaper/pfile_reaper.py <path>
./reaper/dicom_reaper.py <host> <port> <return port> reaper <scanner AET>
./reaper/dicom_file_reaper.py <path>
./reaper/meeg_file_reaper.py <path>

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
