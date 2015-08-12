### Installation

```
virtualenv reaperenv
source reaperenv/bin/activate
pip install -U pip setuptools

pip install -r requirements.txt .
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
./reaper/meeg_file_reaper.py -s 1 -u localhost <path>
```
