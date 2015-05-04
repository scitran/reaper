#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

# TODO:
#   - make aux files part of state
#   - include add pfiles on one uid in state
#   - add custom state comparision function that does not re-reap when pfiles start to be overwritten

import logging
log = logging.getLogger('reaper.pfile')

import os
import re
import glob
import shutil
import datetime

import reaper
import gephysio

import scitran.data.medimg.pfile as scipfile
logging.getLogger('scitran.data').setLevel(logging.INFO)


class PFileReaper(reaper.Reaper):

    def __init__(self, options):
        if not os.path.isdir(options.get('path')):
            log.error('path argument must be a directory')
            sys.exit(1)
        self.data_glob = os.path.join(options.get('path'), 'P?????.7')
        super(PFileReaper, self).__init__(options.get('path').strip('/').replace('/', '_'), options)
        self.anonymize = options.get('anonymize')
        self.whitelist = options.get('whitelist').replace('*','.*')
        self.blacklist = options.get('blacklist').split()
        self.peripheral_data_reapers['gephysio'] = gephysio.reap

    def state_str(self, _id, state):
        return '%s, [%s, %s]' % (_id, state['mod_time'].strftime(reaper.DATE_FORMAT), reaper.hrsize(state['size']))

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

    def reap(self, _id, item, tempdir):
        try:
            pfile = scipfile.PFile(item['path'], timezone=self.timezone)
        except (IOError, scipfile.PFileError):
            success = None
            log.warning('skipping     %s (disappeared or unparsable)' % _id)
        else:
            if pfile.patient_id.strip('/').lower() in self.blacklist:
                success = None
                log.info('discarding   %s' % _id)
            elif not re.match(self.whitelist, pfile.patient_id):
                success = None
                log.info('ignoring     %s (non-matching patient ID)' % _id)
            else:
                name_prefix = pfile.series_uid + '_' + str(pfile.acq_no)
                reap_path = tempdir + '/' + name_prefix + '_' + scipfile.PFile.filetype
                os.mkdir(reap_path)
                auxfiles = [(ap, _id + '_' + ap.rsplit('_', 1)[-1]) for ap in glob.glob(item['path'] + '_' + pfile.series_uid + '_*')]
                log.debug('staging      %s%s' % (_id, ', ' + ', '.join([af[1] for af in auxfiles]) if auxfiles else ''))
                os.symlink(item['path'], os.path.join(reap_path, _id))
                for af in auxfiles:
                    os.symlink(af[0], os.path.join(reap_path, af[1]))
                pfile_size = reaper.hrsize(item['state']['size'])
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
                reap_start = datetime.datetime.utcnow()
                auxfile_str = ' + %d aux files' % len(auxfiles) if auxfiles else ''
                log.info('reaping.tgz  %s [%s%s]' % (_id, pfile_size, auxfile_str))
                try:
                    reaper.create_archive(reap_path+'.tgz', reap_path, os.path.basename(reap_path), metadata, dereference=True, compresslevel=4)
                    shutil.rmtree(reap_path)
                except (IOError):
                    success = False
                    log.warning('reap error   %s%s' % (_id, ' or aux files' if auxfiles else ''))
                else:
                    success = True
                    reap_time = (datetime.datetime.utcnow() - reap_start).total_seconds()
                    log.info('reaped.tgz   %s [%s%s] in %.1fs' % (_id, pfile_size, auxfile_str, reap_time))
                    self.reap_peripheral_data(tempdir, pfile, name_prefix, _id)
        return success


if __name__ == '__main__':
    positional_args = [
        (('path',), dict(help='path to PFiles')),
    ]
    optional_args = [
        (('-A', '--no-anonymize'), dict(dest='anonymize', action='store_false', help='do not anonymize patient name and birthdate')),
        (('-b', '--blacklist'), dict(default='discard', help='space-separated list of identifiers to discard ["discard"]')),
        (('-w', '--whitelist'), dict(default='*', help='glob for identifiers to reap ["*"]')),
        (('-i', '--identifier'), dict(default='PatientID', help='metadata field to use for identification ["PatientID"]')),
    ]
    reaper.main(PFileReaper, positional_args, optional_args)
