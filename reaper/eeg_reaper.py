""" SciTran EEG Reaper """

import os
import sys
import glob
import shutil
import logging
import datetime

from . import util
from . import reaper

log = logging.getLogger('reaper.eeg')

FILETYPE = 'eeg'


class EEGReaper(reaper.Reaper):

    """EEGReaper class"""

    def __init__(self, options):
        if not os.path.isdir(options.get('path')):
            log.error('path argument must be a directory')
            sys.exit(1)
        self.data_glob = os.path.join(options.get('path'), '*', '*', '*', '*', '*.eeg')
        super(EEGReaper, self).__init__(options.get('path').strip('/').replace('/', '_'), options)

    def state_str(self, _id, state):
        return '%s, [%s, %s]' % (_id, state['mod_time'].strftime(reaper.DATE_FORMAT), util.hrsize(state['size']))

    def instrument_query(self):
        i_state = {}
        try:
            filepaths = glob.glob(self.data_glob)
            if not filepaths:
                raise Warning('no matching files found (or error while checking for files)')
        except (OSError, Warning) as ex:
            filepaths = []
            log.warning(ex)
        for fp in filepaths:
            eeg = EEGFile(fp)
            i_state[eeg.reap_id] = reaper.ReaperItem(eeg.reap_state, path=fp)
        return i_state

    def reap(self, _id, item, tempdir):
        try:
            eeg = EEGFile(item['path'])
        except AssertionError:
            log.warning('skipping     %s (disappeared or unreadable)', _id)
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
            filepath = util.create_archive(reap_path, os.path.basename(reap_path))
            shutil.rmtree(reap_path)
        # pylint: disable=broad-except
        except Exception:
            log.warning('reap error   %s', _id)
            return False, None
        metadata = util.object_metadata(eeg, self.timezone, os.path.basename(filepath))
        util.set_archive_metadata(filepath, metadata)
        reap_time = (datetime.datetime.utcnow() - reap_start).total_seconds()
        log.info('reaped.zip   %s [%s] in %.1fs', _id, eeg_size, reap_time)
        return True, {filepath: metadata}


class EEGFile(object):

    """EEGFile class"""

    # pylint: disable=too-few-public-methods

    def __init__(self, filepath):
        assert os.access(filepath, os.R_OK)
        self.filepath = filepath

        name = os.path.splitext(os.path.basename(filepath))[0]
        self.acquisition_uid = name

        path = os.path.dirname(filepath)
        path, self.session_uid = os.path.split(path)
        path, self.subject_code = os.path.split(path)
        path, self.project_label = os.path.split(path)
        path, self.group__id = os.path.split(path)

        self.acquisition_timestamp = datetime.datetime.utcfromtimestamp(os.stat(filepath).st_ctime)
        self.file_type = FILETYPE
        self.reap_id = self.session_uid + self.acquisition_uid

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
    ap.add_argument('path', help='path to EEG files')

    return ap


def main():
    # pylint: disable=missing-docstring
    reaper.main(EEGReaper, update_arg_parser)
