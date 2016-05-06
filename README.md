### Installation

#### Python and pip

##### On Ubuntu Server 14.04
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
```

##### On Ubuntu Server 16.04
```
sudo apt-get install python-pip
sudo pip install -U pip setuptools wheel ipython virtualenv
```

#### Virtualenv
```
virtualenv --prompt "(reaper)" reaperenv
source reaperenv/bin/activate
```

#### DCMTK (only needed for DICOM reaping)
Compile DCMTK from source, with promiscuous mode patch applied.
```
(
cd /tmp
curl http://dicom.offis.de/download/dcmtk/snapshot/old/dcmtk-3.6.1_20150924.tar.gz | tar xz
cd dcmtk-*
curl https://raw.githubusercontent.com/scitran/reaper/master/movescu.cc.patch | patch --strip 1
./configure --prefix=$VIRTUAL_ENV
make all
make install
)
```

#### Reaper
```
git clone https://github.com/scitran/reaper.git && cd reaper
python setup.py develop
```


### Debugging

```
AEC=scanner; HOST=host; PORT=port
findscu --verbose -S -aet reaper -aec $AEC -k QueryRetrieveLevel="STUDY"  -k StudyDate="" $HOST $PORT
findscu --verbose -S -aet reaper -aec $AEC -k QueryRetrieveLevel="SERIES" -k StudyDate="" $HOST $PORT
```


### Development

```
./reaper/meeg_file_reaper.py -s 1 -i -u https://localhost:8443/api/reaper?secret=change-me <path>
```

### Folder Reaper Schema
```
# 1. Files not supported at scitran-group or subject-label.
# 2. Multiple files/folders supported at all levels where single file/folders are.
$ tree /testdata/
/testdata/
└── scitran-group
    └── scitran-project
        ├── project-file-attachment
        └── subject-label
            └── session-label
                ├── session-file-attachment
                └── acquisition-label
                    ├── no-type-file
                    └── data-type
                        ├── data-file-1
                        └── data-file-2

```
