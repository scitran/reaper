#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

"""
"""

import logging
log = logging.getLogger('reaper.dicom')

import os
import re
import sys
import json
import dicom
import shutil
import hashlib
import datetime

import reaper


class DicomFileReaper(reaper.Reaper):

    def __init__(self, options):
        self.path = options.get('path')
        if not os.path.exists(self.path):
            os.mkdir(self.path)
            log.info(self.path + ' dost not exist ==> creating...')
        elif not os.path.isdir(self.path):
            log.error('path argument must be a directory')
            sys.exit(1)
        self.destructive = options.get('destructive')
        super(DicomFileReaper, self).__init__(self.path.strip('/').replace('/', '_'), options)

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
            if os.path.samefile(dirpath, self.path):
                continue # ignore files at top-level of self.path
            if not dirnames and filenames:
                try:
                    state = {
                        'mod_time': datetime.datetime.utcfromtimestamp(os.path.getmtime(dirpath)),
                        'file_cnt': len(filenames),
                        'size': sum([os.path.getsize(dirpath + '/' + fn) for fn in filenames]),
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
        reap_path = tempdir + '/' + 'reap'
        os.mkdir(reap_path)
        metadata_path = tempdir + '/' + 'METADATA.json'
        for fn in os.listdir(item['path']):
            fp = item['path'] + '/' + fn
            if fn == 'metadata.json' or fn == 'METADATA.json':
                shutil.move(fp, metadata_path)
            else:
                try:
                    dcm = dicom.read_file(fp, stop_before_pixels=True)
                except:
                    pass
                else:
                    reap_cnt += 1
                    #dcm.save_as(reap_path + '/' + fn)
                    if self.destructive:
                        shutil.move(fp, reap_path + '/' + fn)
                    else:
                        shutil.copyfile(fp, reap_path + '/' + fn)
        log.info('reaped       %s (%d images) in %.1fs' % (_id, reap_cnt, (datetime.datetime.utcnow() - reap_start).total_seconds()))
        metadata = {}
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r') as metadata_file:
                metadata = json.load(metadata_file, object_hook=reaper.datetime_decoder)
            os.remove(metadata_path)
        metadata['filetype'] = 'dicom'
        log.info('compressing  %s' % _id)
        reaper.create_archive(reap_path+'.tgz', reap_path, os.path.basename(reap_path), metadata, compresslevel=6)
        shutil.rmtree(reap_path)
        if self.destructive:
            shutil.rmtree(item['path'])
        return True


if __name__ == '__main__':
    positional_args = [
        (('path',), dict(help='path to DICOM files')),
    ]
    optional_args = [
        (('-d', '--destructive'), dict(action='store_true', help='delete DICOM files after reaping')),
    ]
    reaper.main(DicomFileReaper, positional_args, optional_args)
