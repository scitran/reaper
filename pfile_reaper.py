#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

import logging
log = logging.getLogger('reaper.pfile')

import os
import re
import glob
import shutil
import datetime

import reaper
import gephysio
import tempdir as tempfile

import scitran.data.medimg.pfile as scipfile
logging.getLogger('scitran.data').setLevel(logging.INFO)


class PFileReaper(reaper.Reaper):

    def __init__(self, options):
        self.data_glob = os.path.join(options.path, 'P?????.7')
        super(PFileReaper, self).__init__(options.path.strip('/').replace('/', '_'), options)
        self.anonymize = options.anonymize
        self.pat_id = options.patid.replace('*','.*')
        self.discard_ids = options.discard.split()
        self.peripheral_data_reapers['gephysio'] = gephysio.reap

    def state_str(self, state):
        return state['mod_time'].strftime(reaper.DATE_FORMAT) + ', ' + reaper.hrsize(state['size'])

    def instrument_query(self):
        i_state = {}
        try:
            filepaths = glob.glob(self.data_glob)
            if not filepaths:
                raise Warning('no matching files found (or error while checking for files)')
        except (OSError, Warning) as e:
            filepaths = []
            log.warning(e)
        for fp in filepaths:
            stats = os.stat(fp)
            state = {
                    'mod_time': datetime.datetime.utcfromtimestamp(stats.st_mtime),
                    'size': stats.st_size,
                    }
            i_state[os.path.basename(fp)] = reaper.ReaperItem(state, path=fp)
        return i_state

    def reap(self, _id, item):
        try:
            pfile = scipfile.PFile(item['path'], timezone=self.timezone)
        except scipfile.PFileError:
            pfile = None
            success = True
            log.warning('skipping     %s (unparsable)' % _id)
        else:
            if pfile.patient_id.strip('/').lower() in self.discard_ids:
                success = True
                log.info('discarding   %s' % _id)
            elif not re.match(self.pat_id, pfile.patient_id):
                success = True
                log.info('ignoring     %s (non-matching patient ID)' % _id)
            else:
                name_prefix = pfile.series_uid + '_' + str(pfile.acq_no)
                with tempfile.TemporaryDirectory(dir=self.tempdir) as tempdir_path:
                    reap_path = tempdir_path + '/' + name_prefix + '_' + scipfile.PFile.filetype
                    os.mkdir(reap_path)
                    auxfiles = [(ap, _id + '_' + ap.rsplit('_', 1)[-1]) for ap in glob.glob(item['path'] + '_' + pfile.series_uid + '_*')]
                    log.debug('staging      %s%s' % (_id, ', ' + ', '.join([af[1] for af in auxfiles]) if auxfiles else ''))
                    os.symlink(item['path'], os.path.join(reap_path, _id))
                    for af in auxfiles:
                        os.symlink(af[0], os.path.join(reap_path, af[1]))
                    pfile_size = reaper.hrsize(item['state']['size'])
                    log.info('reaping.tgz  %s [%s%s]' % (_id, pfile_size, ' + %d aux files' % len(auxfiles) if auxfiles else ''))
                    metadata = {
                        'filetype': scipfile.PFile.filetype,
                        'timezone': self.timezone,
                        'header': {
                            'group': pfile.nims_group_id,
                            'project': pfile.nims_project,
                            'session': pfile.nims_session_id,
                            'session_no': pfile.series_no,
                            'session_desc': pfile.series_desc,
                            'acquisition': pfile.nims_acquisition_id,
                            'acquisition_no': pfile.acq_no,
                            'timestamp': pfile.nims_timestamp,
                        },
                    }
                    try:
                        reaper.create_archive(reap_path+'.tgz', reap_path, os.path.basename(reap_path), metadata, dereference=True, compresslevel=4)
                        shutil.rmtree(reap_path)
                    except (IOError):
                        success = False
                        log.warning('reap error   %s%s' % (_id, ' or aux files' if auxfiles else ''))
                    else:
                        self.reap_peripheral_data(tempdir_path, pfile, name_prefix, _id)
                        if self.upload(tempdir_path, _id):
                            success = True
                            log.info('done         %s' % _id)
                        else:
                            success = False
        return success

    def is_auxfile(self, filepath):
        if open(filepath).read(32) == self.pfile.series_uid:
            return True
        try:
            return (scipfile.PFile(filepath).series_uid == self.pfile.series_uid)
        except scipfile.PFileError:
            return False


if __name__ == '__main__':
    positional_args = [
        (('path',), dict(help='path to PFiles')),
    ]
    optional_args = [
        (('-A', '--no-anonymize'), dict(dest='anonymize', action='store_false', help='do not anonymize patient name and birthdate')),
        (('-d', '--discard'), dict(default='discard', help='space-separated list of Patient IDs to discard')),
        (('-i', '--patid'), dict(default='*', help='glob for Patient IDs to reap ["*"]')),
    ]
    reaper.main(PFileReaper, positional_args, optional_args)
