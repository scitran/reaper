#!/usr/bin/env python
#
# @author:  Eric Larson

"""
M/EEG file reaper
"""

import logging
log = logging.getLogger('reaper.meeg')
log.setLevel(logging.INFO)

import os
import sys
import shutil
import datetime
import warnings

import reaper


class MEEGFileReaper(reaper.Reaper):

    def __init__(self, options):
        self.path = options.get('path')
        if not os.path.exists(self.path):
            os.mkdir(self.path)
            log.info(self.path + ' dost not exist ==> creating...')
        elif not os.path.isdir(self.path):
            log.error('path argument must be a directory')
            sys.exit(1)
        else:
            log.info('Monitoring acquisition directory %s' % self.path)
        self.destructive = options.get('destructive')
        super(MEEGFileReaper, self).__init__(
            self.path.strip('/').replace('/', '_'), options)

    def state_str(self, _id, state):
        return '%s [%s, %d files, %s]' % (
            _id,
            state['mod_time'].strftime(reaper.DATE_FORMAT),
            state['file_cnt'],
            reaper.hrsize(state['size']),
        )

    def instrument_query(self):
        i_state = {}
        for dirpath, dirnames, filenames in os.walk(self.path):
            if os.path.basename(dirpath).startswith('.'):
                continue  # ignore dotdirectories
            if os.path.samefile(dirpath, self.path):
                continue  # ignore files at top-level of self.path
            if len(dirnames) > 0 or len(filenames) == 0:
                continue
            try:
                mtime = os.path.getmtime(dirpath)
                state = {
                    'mod_time': datetime.datetime.utcfromtimestamp(mtime),
                    'file_cnt': len(filenames),
                    'size': sum([os.path.getsize(os.path.join(dirpath, fn))
                                 for fn in filenames]),
                }
            except:
                pass
            else:
                i_state[dirpath] = reaper.ReaperItem(state, path=dirpath)
        return i_state

    def reap(self, _id, item, tempdir):
        reap_start = datetime.datetime.utcnow()
        log.info('reaping      %s' % self.state_str(_id, item['state']))
        reap_cnt = 0
        reap_path = os.path.join(tempdir, 'reap')
        os.mkdir(reap_path)
        for fn in os.listdir(item['path']):
            fp = os.path.join(item['path'], fn)
            try:
                # catch warnings here because some recordings have a
                # shielding mode that will throw a warning on read
                import mne
                with warnings.catch_warnings(record=True):
                    mne.io.read_raw_fif(fp, allow_maxshield=True)
            except Exception:
                pass
            else:
                reap_cnt += 1
                shutil.copyfile(fp, reap_path + '/' + fn)
        t = (datetime.datetime.utcnow() - reap_start).total_seconds()
        log.info('reaped       %s (%d images) in %.1fs' % (_id, reap_cnt, t))

        # project is the third-level dir name (project/subject/data/x_raw.fif)
        project = \
            os.path.split(os.path.split(os.path.split(item['path'])[0])[0])[1]

        metadata = {
            'filetype': 'FIF',
            'timezone': self.timezone,
            'header': {
                'project': project,
            },
        }

        log.info('compressing  %s' % _id)
        reaper.create_archive(reap_path + '.zip', reap_path,
                              os.path.basename(reap_path), metadata)
        shutil.rmtree(reap_path)
        return True

    def destroy(self, item):
        shutil.rmtree(item['path'])


def main():
    positional_args = [
        (('path',), dict(help='path to MEEG files')),
    ]
    optional_args = [
    ]
    reaper.main(MEEGFileReaper, positional_args, optional_args)


if __name__ == '__main__':
    main()
