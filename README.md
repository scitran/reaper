[![Build Status](https://travis-ci.org/scitran/reaper.svg?branch=master)](https://travis-ci.org/scitran/reaper)

### Installation
```
virtualenv --prompt "(reaper) " reaperenv
source reaperenv/bin/activate
pip install git+https://github.com/scitran/reaper.git
```

More detailed [installation instructions](https://github.com/scitran/reaper/blob/master/INSTALLATION.md) are also available.

### Folder Sniper File System Schema

Multiple files/folders are supported at all levels, except at the scitran-group level, which does not support files at all.
```
$ tree example-tree
example-tree
└── scitran-group
    └── scitran-project
        ├── project-file
        └── subject-label
            ├── subject-file
            └── session-label
                ├── session-file
                └── acquisition-label
                    ├── untyped-data-file
                    └── data-type
                        └── data-file
```

### Windows eeg_reaper.exe creation
1. Download and install [python](https://www.python.org/ftp/python/2.7.13/python-2.7.13.msi) (and [msvc](https://www.microsoft.com/en-us/download/details.aspx?id=44266))
2. Download and unzip [scitran/reaper](https://github.com/scitran/reaper/archive/master.zip)
3. `$ pip install pyinstaller --editable .` - in extracted reaper folder
4. `$ pyinstaller --onefile bin/eeg_reaper` - creates executable in dist/

Notes:
* those unfamiliar with windows may find [cmder](https://github.com/cmderdev/cmder/releases/download/v1.3.2/cmder.zip) useful
* system-wide `pip install` requires a shell started via right-click + 'Run as Administrator'
