#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" SciTran EEG Reaper """

import os
import sys
import glob
import shutil
import logging
import argparse
import datetime

from . import util
from . import reaper

log = logging.getLogger('reaper.eeg')

FILETYPE = 'eeg'

DESCRIPTION = u"""
This reaper will monitor a given directory for EEG files created with
BrainVision Recorder and upload them together with their header (.vhdr)
and marker (.vmrk) files to a scitran/core-compatible API, including
creation of the appropriate project/session/acquisition hierarchy.

The hierarchy is inferred from the EEG filename segments separated by
underscores and/or the directory structure. The acquisition uid may
be omitted in which case the creation timestamp will be used instead.

Raw Files
├── group-id_project-label_subject-code_session-uid_acquisition-uid.eeg
└── group-id
    └── project-label
        ├── subject-code_session-uid_acquisition-uid.eeg
        └── subject-code
            └── session-uid
                └── acquisition-uid.eeg
"""


class EEGReaper(reaper.Reaper):

    """EEGReaper class"""

    has_mapkey_arg = False
    has_opt_arg = False

    def __init__(self, options):
        path = options.get('path')
        if not os.path.isdir(path):
            log.error('path argument must be a directory')
            sys.exit(1)
        super(EEGReaper, self).__init__(path.strip('/').replace('/', '_'), options)
        self.path = path

    def state_str(self, _id, state):
        return '%s, [%s, %s]' % (_id, state['mod_time'].strftime(reaper.DATE_FORMAT), util.hrsize(state['size']))

    def instrument_query(self):
        i_state = {}
        try:
            # list every path/**/*.eeg file (using os.walk because python2 glob doesn't support **)
            filepaths = [fp for w in os.walk(self.path) for fp in glob.glob(os.path.join(w[0], '*.eeg'))]
            if not filepaths:
                raise Warning('no matching files found (or error while checking for files)')
        except (OSError, Warning) as ex:
            filepaths = []
            log.warning(ex)
        for fp in filepaths:
            try:
                eeg = EEGFile(fp, self.path)
            except (IOError, EEGFileError):
                # TBD should this be logged (repeatedly) here?
                continue
            i_state[eeg.acquisition_uid] = reaper.ReaperItem(eeg.reap_state, path=fp)
        return i_state

    def reap(self, _id, item, tempdir):
        try:
            eeg = EEGFile(item['path'], self.path)
        except (IOError, EEGFileError):
            log.warning('skipping     %s (disappeared or unparsable)', _id)
            return None, {}

        filepaths = sorted(glob.glob(os.path.splitext(item['path'])[0] + '.*'))
        filenames = [(fp, os.path.basename(fp)) for fp in filepaths]
        log.debug('staging      %s%s', _id, ', ' + ', '.join([fn[1] for fn in filenames]))
        reap_path = os.path.join(tempdir, _id)
        os.mkdir(reap_path)
        for fp, fn in filenames:
            os.symlink(fp, os.path.join(reap_path, fn))

        eeg_size = util.hrsize(item['state']['size'])
        reap_start = datetime.datetime.utcnow()
        log.info('reaping.zip  %s [%s]', _id, eeg_size)
        try:
            filepath = util.create_archive(reap_path, os.path.basename(reap_path) + '.eeg', rootdir=False)
            shutil.rmtree(reap_path)
        # pylint: disable=broad-except
        except Exception:
            log.warning('reap error   %s', _id)
            return False, None
        metadata = util.object_metadata(eeg, self.timezone, os.path.basename(filepath))
        metadata['acquisition']['files'][0]['info'] = {'path': item['path']}
        util.set_archive_metadata(filepath, metadata)
        reap_time = (datetime.datetime.utcnow() - reap_start).total_seconds()
        log.info('reaped.zip   %s [%s] in %.1fs', _id, eeg_size, reap_time)
        return True, {filepath: metadata}


class EEGFileError(Exception):
    # pylint: disable=missing-docstring
    pass


class EEGFile(object):

    """EEGFile class"""

    # pylint: disable=too-few-public-methods

    def __init__(self, filepath, reaperpath):
        with open(filepath, 'rb'):
            self.filepath = filepath

        # the .eeg file's ctime changes when appended, using header's ctime instead
        header = os.path.splitext(filepath)[0] + '.vhdr'
        creation_time = os.stat(header).st_ctime

        relpath = os.path.relpath(filepath, reaperpath)
        dirpath, filename = os.path.split(relpath)
        hierarchy_info = dirpath.split('/') if dirpath else []
        filename_info = os.path.splitext(filename)[0].split('_')
        sort_info = hierarchy_info + list(filter(None, filename_info))

        # not enough data to infer all sorting levels
        if len(sort_info) < 4:
            # TBD should reaper support setting group[project] at startup to ease this?
            # TBD these won't even be discovered making it hard to trace why it wasn't UL'd
            raise EEGFileError('cannot infer sorting info from ' + relpath)

        # autogenerate last level (acquisition_uid) if not provided
        if len(sort_info) < 5:
            dt = datetime.datetime.utcfromtimestamp(creation_time)
            sort_info.append(dt.strftime('%Y%m%d_%H%M%S'))

        # discard all but the last 5 sort info parts
        if len(sort_info) > 5:
            # TBD should this be handled differently?
            # scenarios: hierarchy deep, too many _'s in filename or both
            sort_info = sort_info[-5:]

        self.group__id = sort_info[0]
        self.project_label = sort_info[1]
        self.subject_code = sort_info[2]
        self.session_uid = sort_info[3]
        self.acquisition_uid = sort_info[4]

        self.acquisition_timestamp = datetime.datetime.utcfromtimestamp(creation_time)
        self.file_type = FILETYPE

    @property
    def reap_state(self):
        """Return ReaperItem compatible state"""
        stats = os.stat(self.filepath)
        return {
            'mod_time': datetime.datetime.utcfromtimestamp(stats.st_mtime),
            'size': stats.st_size,
        }


def update_arg_parser(ap):
    # pylint: disable=missing-docstring
    ap.add_argument('path', help='path to "Raw Files"')
    ap.description = DESCRIPTION
    ap.formatter_class=argparse.RawDescriptionHelpFormatter

    return ap


def main():
    # pylint: disable=missing-docstring
    reaper.main(EEGReaper, update_arg_parser)
