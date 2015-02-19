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
logging.getLogger('scitran.data').setLevel(logging.INFO) #FIXME


class PFileReaper(reaper.Reaper):

    def __init__(self, data_path, options):
        self.data_glob = os.path.join(data_path, 'P?????.7')
        id_ = data_path.strip('/').replace('/', '_')
        super(PFileReaper, self).__init__(id_, options)
        self.peripheral_data_reapers['gephysio'] = gephysio.reap

    def state_str(self, state):
        return state['mod_time'].strftime(reaper.DATE_FORMAT) + ', ' + reaper.hrsize(state['size'])

    def instrument_query(self):
        state = {}
        try:
            filepaths = glob.glob(self.data_glob)
            if not filepaths:
                raise Warning('no matching files found (or error while checking for files)')
        except (OSError, Warning) as e:
            filepaths = []
            log.warning(e)
        for fp in filepaths:
            fn = os.path.basename(fp)
            stats = os.stat(fp)
            state[fn] = {
                '_id': fn,
                'path': fp,
                'state': {
                    'mod_time': datetime.datetime.utcfromtimestamp(stats.st_mtime),
                    'size': stats.st_size
                },
            }
        return state

    def reap(self, item):
        try:
            pfile = scipfile.PFile(item['path'])
        except scipfile.PFileError:
            pfile = None
            success = True
            log.warning('skipping     %s (unparsable)' % item['_id'])
        else:
            if pfile.patient_id.strip('/').lower() in self.options.discard_ids:
                success = True
                log.info('discarding   %s' % item['_id'])
            elif not re.match(self.options.pat_id, pfile.patient_id):
                success = True
                log.info('ignoring     %s (non-matching patient ID)' % item['_id'])
            else:
                name_prefix = pfile.series_uid + '_' + str(pfile.acq_no)
                with tempfile.TemporaryDirectory(dir=self.options.tempdir) as tempdir_path:
                    reap_path = '%s/%s_pfile' % (tempdir_path, name_prefix)
                    os.mkdir(reap_path)
                    auxfiles = [(ap, item['_id'] + '_' + ap.rsplit('_', 1)[-1]) for ap in glob.glob(item['path'] + '_' + pfile.series_uid + '_*')]
                    log.debug('staging      %s%s' % (item['_id'], ', ' + ', '.join([af[1] for af in auxfiles]) if auxfiles else ''))
                    os.symlink(item['path'], os.path.join(reap_path, item['_id']))
                    for af in auxfiles:
                        os.symlink(af[0], os.path.join(reap_path, af[1]))
                    pfile_size = reaper.hrsize(item['state']['size'])
                    log.info('reaping.tgz  %s [%s%s]' % (item['_id'], pfile_size, ' + %d aux files' % len(auxfiles) if auxfiles else ''))
                    metadata = {
                        'filetype': scipfile.PFile.filetype,
                        'header': {
                            'group': pfile.nims_group_id,
                            'project': pfile.nims_project,
                            'session': pfile.nims_session_id,
                            'acquisition': pfile.nims_acquisition_id,
                            'timestamp': pfile.nims_timestamp,
                        },
                    }
                    try:
                        reaper.create_archive(reap_path+'.tgz', reap_path, os.path.basename(reap_path), metadata, dereference=True, compresslevel=4)
                        shutil.rmtree(reap_path)
                    except (IOError):
                        success = False
                        log.warning('reap error   %s%s' % (item['_id'], ' or aux files' if auxfiles else ''))
                    else:
                        self.reap_peripheral_data(tempdir_path, pfile, name_prefix, item['_id'])
                        if self.upload(tempdir_path, item['_id']):
                            success = True
                            log.info('done         %s' % item['_id'])
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
    reaper.main(PFileReaper)
