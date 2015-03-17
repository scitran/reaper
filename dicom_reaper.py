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
logging.getLogger('scitran.data').setLevel(logging.INFO)


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

    def __init__(self, options):
        self.scu = scu.SCU(options.host, options.port, options.return_port, options.aet, options.aec)
        super(DicomReaper, self).__init__(self.scu.aec, options)
        self.anonymize = options.anonymize
        self.pat_id = options.patid.replace('*','.*')
        self.discard_ids = options.discard.split()
        self.peripheral_data_reapers['gephysio'] = gephysio.reap

    def state_str(self, state):
        return ', '.join(['%s %s' % (v, k) for k, v in state.iteritems()])

    def instrument_query(self):
        i_state = {}
        scu_resp = self.scu.find(scu.SeriesQuery(**self.query_params))
        for r in scu_resp:
            state = {
                    'images': int(r['NumberOfSeriesRelatedInstances']),
                    }
            i_state[r['SeriesInstanceUID']] = reaper.ReaperItem(state)
        return i_state

    def reap(self, _id, item):
        if item['state']['images'] == 0:
            log.info('ignoring     %s (zero images)' % _id)
            return True
        log.info('reaping      %s (%s)' % (_id, self.state_str(item['state'])))
        with tempfile.TemporaryDirectory(dir=self.tempdir) as tempdir_path:
            reap_cnt = self.scu.move(scu.SeriesQuery(StudyInstanceUID='', SeriesInstanceUID=_id), tempdir_path)
            filepaths = [os.path.join(tempdir_path, filename) for filename in os.listdir(tempdir_path)]
            log.info('reaped       %s (%d images)' % (_id, reap_cnt))
            if reap_cnt > 0:
                dcm = self.DicomFile(filepaths[0])
                if dcm.patient_id.strip('/').lower() in self.discard_ids:
                    log.info('discarding   %s' % _id)
                    return True
                if not re.match(self.pat_id, dcm.patient_id):
                    log.info('ignoring     %s (non-matching patient ID)' % _id)
                    return True
            if reap_cnt == item['state']['images']:
                acq_info = self.split_into_acquisitions(_id, item, tempdir_path, filepaths)
                for ai in acq_info:
                    dcm = scidcm.Dicom(ai['path'], timezone=self.timezone)
                    self.reap_peripheral_data(tempdir_path, dcm, ai['prefix'], ai['log_info'])
                success = self.upload(tempdir_path, ai['log_info'])
                if success:
                    log.info('completed    %s' % _id)
            else:
                success = False
        return success

    def split_into_acquisitions(self, _id, item, path, filepaths):
        if self.anonymize:
            log.info('anonymizing  %s' % _id)
        dcm_dict = {}
        for filepath in filepaths:
            dcm = self.DicomFile(filepath, self.anonymize)
            if os.path.basename(filepath).startswith('(none)'):
                new_filepath = filepath.replace('(none)', 'NA')
                os.rename(filepath, new_filepath)
                filepath = new_filepath
            os.utime(filepath, (int(dcm.timestamp.strftime('%s')), int(dcm.timestamp.strftime('%s'))))  # correct timestamps
            dcm_dict.setdefault(dcm.acq_no, []).append(filepath)
        log.info('compressing  %s' % _id)
        acq_info = []
        for acq_no, acq_paths in dcm_dict.iteritems():
            name_prefix = _id + ('_' + str(acq_no) if acq_no is not None else '')
            dir_name = name_prefix + '_' + scidcm.Dicom.filetype
            arcdir_path = os.path.join(path, dir_name)
            os.mkdir(arcdir_path)
            for filepath in acq_paths:
                os.rename(filepath, '%s.dcm' % os.path.join(arcdir_path, os.path.basename(filepath)))
            metadata = {
                    'filetype': scidcm.Dicom.filetype,
                    'timezone': self.timezone,
                    'overwrite': {
                        'firstname_hash': dcm.firstname_hash,
                        'lastname_hash': dcm.lastname_hash,
                        }
                    }
            reaper.create_archive(arcdir_path+'.tgz', arcdir_path, dir_name, metadata, compresslevel=6)
            shutil.rmtree(arcdir_path)
            acq_info.append({
                    'path': arcdir_path+'.tgz',
                    'prefix': name_prefix,
                    'log_info': '%s%s' % (_id, '.' + str(acq_no) if acq_no is not None else ''),
                    })
        return acq_info


    class DicomFile(object):

        def __init__(self, filepath, anonymize=False):
            dcm = dicom.read_file(filepath, stop_before_pixels=(not anonymize))
            acq_datetime = scidcm.timestamp(dcm.get('AcquisitionDate'), dcm.get('AcquisitionTime'))
            study_datetime = scidcm.timestamp(dcm.get('StudyDate'), dcm.get('StudyTime'))
            self.timestamp = acq_datetime or study_datetime
            self.acq_no = int(dcm.get('AcquisitionNumber', 1)) if dcm.get('Manufacturer').upper() != 'SIEMENS' else None
            self.patient_id = dcm.get('PatientID', '')
            self.firstname_hash = None
            self.lastname_hash = None
            if anonymize:
                firstname, lastname = scidcm.parse_patient_name(dcm.get('PatientName', ''))
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
    positional_args = [
        (('host',), dict(help='remote hostname or IP')),
        (('port',), dict(help='remote port')),
        (('return_port',), dict(help='local return port')),
        (('aet',), dict(help='local AE title')),
        (('aec',), dict(help='remote AE title')),
    ]
    optional_args = [
        (('-A', '--no-anonymize'), dict(dest='anonymize', action='store_false', help='do not anonymize patient name and birthdate')),
        (('-d', '--discard'), dict(default='discard', help='space-separated list of Patient IDs to discard')),
        (('-i', '--patid'), dict(default='*', help='glob for Patient IDs to reap ["*"]')),
    ]
    reaper.main(DicomReaper, positional_args, optional_args)
