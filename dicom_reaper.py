#!/usr/bin/env python
#
# @author:  Gunnar Schaefer

"""
apt-get -V install ipython python-virtualenv python-dev dcmtk
adduser --disabled-password --uid 1000 --gecos "Scitran Reaper" reaper
"""

import logging
log = logging.getLogger('reaper.dicom')
logging.getLogger('reaper.dicom.scu').setLevel(logging.INFO)

import os
import re
import time
import dicom
import shutil
import hashlib
import datetime

import scu
import reaper
import gephysio
import tempdir as tempfile

import scitran.data.medimg.dcm as scidcm
logging.getLogger('scitran.data').setLevel(logging.INFO) #FIXME


class DicomReaper(reaper.Reaper):

    query_params = {
        'StudyInstanceUID': '',
        'SeriesInstanceUID': '',
        'StudyID': '',
        'SeriesNumber': '',
        'SeriesDate': '',
        'SeriesTime': '',
        'NumberOfSeriesRelatedInstances': '',
    }

    def __init__(self, arg_str, options):
        self.scu = scu.SCU(*arg_str.split(':'))
        super(DicomReaper, self).__init__(self.scu.aec, options)
        self.peripheral_data_reapers['gephysio'] = gephysio.reap

    def state_str(self, state):
        return ', '.join(['%s %s' % (v, k) for k, v in state.iteritems()])

    def instrument_query(self):
        state = {}
        scu_resp = self.scu.find(scu.SeriesQuery(**self.query_params))
        for r in scu_resp:
            state[r['SeriesInstanceUID']] = {
                '_id': r['SeriesInstanceUID'],
                'state': {
                    'images': int(r['NumberOfSeriesRelatedInstances']),
                },
            }
        return state

    def reap(self, item):
        if item['state']['images'] == 0:
            log.info('ignoring     %s (zero images)' % item['_id'])
            return True
        log.info('reaping      %s (%s)' % (item['_id'], self.state_str(item['state'])))
        with tempfile.TemporaryDirectory(dir=self.options.tempdir) as tempdir_path:
            reap_cnt = self.scu.move(scu.SeriesQuery(StudyInstanceUID='', SeriesInstanceUID=item['_id']), tempdir_path)
            filepaths = [os.path.join(tempdir_path, filename) for filename in os.listdir(tempdir_path)]
            log.info('reaped       %s (%d images)' % (item['_id'], reap_cnt))
            if reap_cnt > 0:
                dcm = self.DicomFile(filepaths[0])
                if dcm.patient_id.strip('/').lower() in self.options.discard_ids:
                    log.info('discarding   %s' % item['_id'])
                    return True
                if not re.match(self.options.pat_id, dcm.patient_id):
                    log.info('ignoring     %s (non-matching patient ID)' % item['_id'])
                    return True
            if reap_cnt == item['state']['images']:
                acq_info = self.split_into_acquisitions(item, tempdir_path, filepaths)
                for ai in acq_info:
                    self.reap_peripheral_data(tempdir_path, scidcm.Dicom(ai['path']), ai['prefix'], ai['log_info'])
                success = self.upload(tempdir_path, ai['log_info'])
                if success:
                    log.info('completed    %s' % item['_id'])
            else:
                success = False
                item['failures'] += 1
                log.warning('failure      %s (%d failures)' % (item['_id'], item['failures']))
                if item['failures'] > 9:
                    success = True
                    log.warning('abandoning   %s (%s)' % (item['_id'], self.state_str(item['state'])))
        return success

    def split_into_acquisitions(self, item, path, filepaths):
        if self.options.anonymize:
            log.info('anonymizing  %s' % item['_id'])
        dcm_dict = {}
        for filepath in filepaths:
            dcm = self.DicomFile(filepath, self.options.anonymize)
            if os.path.basename(filepath).startswith('(none)'):
                new_filepath = filepath.replace('(none)', 'NA')
                os.rename(filepath, new_filepath)
                filepath = new_filepath
            os.utime(filepath, (int(dcm.timestamp.strftime('%s')), int(dcm.timestamp.strftime('%s'))))  # correct timestamps
            dcm_dict.setdefault(dcm.acq_no, []).append(filepath)
        log.info('compressing  %s' % item['_id'])
        acq_info = []
        for acq_no, acq_paths in dcm_dict.iteritems():
            name_prefix = item['_id'] + ('_' + str(acq_no) if acq_no is not None else '')
            dir_name = name_prefix + '_dicoms'
            arcdir_path = os.path.join(path, dir_name)
            os.mkdir(arcdir_path)
            for filepath in acq_paths:
                os.rename(filepath, '%s.dcm' % os.path.join(arcdir_path, os.path.basename(filepath)))
            metadata = {
                    'filetype': scidcm.Dicom.filetype,
                    'overwrite': {
                        'firstname_hash': dcm.firstname_hash,
                        'lastname_hash': dcm.lastname_hash,
                        'timezone': self.options.timezone,
                        }
                    }
            reaper.create_archive(arcdir_path+'.tgz', arcdir_path, dir_name, metadata, compresslevel=6)
            shutil.rmtree(arcdir_path)
            acq_info.append({
                    'path': arcdir_path+'.tgz',
                    'prefix': name_prefix,
                    'log_info': '%s%s' % (item['_id'], '.' + str(acq_no) if acq_no is not None else ''),
                    })
        return acq_info


    class DicomFile(object):

        def __init__(self, filepath, anonymize=False):
            dcm = dicom.read_file(filepath, stop_before_pixels=(not anonymize))
            acq_datetime = scidcm.timestamp(dcm.get('AcquisitionDate'), dcm.get('AcquisitionTime'))
            study_datetime = scidcm.timestamp(dcm.get('StudyDate'), dcm.get('StudyTime'))
            self.timestamp = acq_datetime or study_datetime
            self.acq_no = int(dcm.get('AcquisitionNumber', 1)) if dcm.get('Manufacturer').upper() != 'SIEMENS' else None
            self.patient_id = dcm.get('PatientID')
            self.firstname_hash = None
            self.lastname_hash = None
            if anonymize:
                firstname, lastname = scidcm.parse_patient_name(dcm.PatientName)
                self.firstname_hash = hashlib.sha256(firstname).hexdigest() if firstname else None
                self.lastname_hash = hashlib.sha256(lastname).hexdigest() if lastname else None
                if dcm.PatientBirthDate:
                    dob = datetime.datetime.strptime(dcm.PatientBirthDate, '%Y%m%d')
                    months = 12 * (self.timestamp.year - dob.year) + (self.timestamp.month - dob.month) - (self.timestamp.day < dob.day)
                    dcm.PatientAge = '%03dM' % months if months < 960 else '%03dY' % (months/12)
                del dcm.PatientName
                del dcm.PatientBirthDate
                dcm.save_as(filepath)


if __name__ == '__main__':
    reaper.main(DicomReaper)
