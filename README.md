### Installation

```
virtualenv reaperenv
source reaperenv/bin/activate
pip install -U pip setuptools

pip install pytz
pip install tzlocal
pip install requests

pip install numpy
pip install git+https://github.com/scitran/pydicom.gitmirror.git@value_mismatch
pip install git+https://github.com/nipy/nibabel.git
pip install git+https://github.com/moloney/dcmstack

git clone https://github.com/scitran/reaper.git
git clone https://github.com/scitran/data.git
pip install -e data
```

### Reaping

```
reaper/pfile_reaper.py <path>
reaper/dicom_reaper.py <host> <port> <return port> reaper <scanner AET>
```


### Debugging

```
findscu --verbose -S -aet reaper -aec <scanner AET> -k QueryRetrieveLevel="STUDY" -k StudyDate="" <host> <port>
findscu --verbose -S -aet reaper -aec <scanner AET> -k QueryRetrieveLevel="SERIES" -k StudyDate="" <host> <port>
```
