[![Build Status](https://travis-ci.org/scitran/reaper.svg?branch=master)](https://travis-ci.org/scitran/reaper)

### Installation
```
virtualenv --prompt "(reaper) " reaperenv
source reaperenv/bin/activate
pip install -e git+https://github.com/scitran/reaper.git#egg=reaper
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
