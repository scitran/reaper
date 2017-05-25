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
            except (IOError, EEGFileError) as ex:
                continue
            i_state[eeg.acquisition_uid] = reaper.ReaperItem(eeg.reap_state, path=fp)
        return i_state

    def reap(self, _id, item, tempdir):
        try:
            eeg = EEGFile(item['path'], self.path)
        except (IOError, EEGFileError) as ex:
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
    pass


class EEGFile(object):

    """EEGFile class"""

    # pylint: disable=too-few-public-methods

    def __init__(self, filepath, reaperpath):
        with open(filepath):
            self.filepath = filepath

        creation_time = os.stat(filepath).st_ctime
        relpath = os.path.relpath(filepath, reaperpath)
        dirpath, filename = os.path.split(relpath)
        hierarchy_info = dirpath.split('/') if dirpath else []
        filename_info = os.path.splitext(filename)[0].split('_')
        sort_info = hierarchy_info + filename_info

        # not enough data to infer all sorting levels
        if len(sort_info) < 4:
            # TBD should reaper support setting group[project] at startup?
            # TBD these won't even be discovered making it hard to trace why it wasn't UL'd
            raise EEGFileError('cannot infer sorting info from ' + relpath)

        # autogenerate last level (acquisition_uid) if needed
        if len(sort_info) < 5:
            # TBD format, timezone?
            dt = datetime.datetime.utcfromtimestamp(creation_time)
            sort_info.append(dt.strftime('%Y%m%d_%H%M%S'))

        # discard all but the last 5 sort info parts
        if len(sort_info) > 5:
            # TBD should this be handled differently?
            # scenarios: hierarchy deep, too many _'s in filename or both
            sort_info = sort_info[-5:]

        sort_keys = ('group__id', 'project_label', 'subject_code', 'session_uid', 'acquisition_uid')
        for i, sort_key in enumerate(sort_keys):
            setattr(self, sort_key, sort_info[i])

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

    return ap


def main():
    # pylint: disable=missing-docstring
    reaper.main(EEGReaper, update_arg_parser)
