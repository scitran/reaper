""" SciTran DICOM Net Reaper """

import os
import shutil
import string
import hashlib
import logging
import datetime

import dicom

from . import scu
from . import util
from . import reaper

log = logging.getLogger('reaper.dicom')

FILETYPE = 'dicom'
GEMS_TYPE_SCREENSHOT = ['DERIVED', 'SECONDARY', 'SCREEN SAVE']
GEMS_TYPE_VXTL = ['DERIVED', 'SECONDARY', 'VXTL STATE']


def parse_id(_id, default_subj_code):
    """
    Parse subject code, group name and project name from an id.

    If the id does not contain a subject code, rely on the supplied default.

    Expected formatting: subj_code@group_name/project_name

    Parameters
    ----------
    _id : str
        _id string from dicom tag
    default_subj_code : str
        subject code to use if _id does not contain a subject code

    Returns
    -------
    subj_code : str
        string of subject identifer
    group_name : str
        string of group name
    project_name : str
        string of project name

    """
    subj_code = group_name = exp_name = None
    if _id is not None:
        subj_code, _, lab_info = _id.strip(string.punctuation + string.whitespace).rpartition('@')
        group_name, _, exp_name = lab_info.partition('/')
    return subj_code or default_subj_code, group_name, exp_name


class DicomNetReaper(reaper.Reaper):

    """DicomNetReaper class"""

    query_params = {  # FIXME dedup with scu.SCUQuery
        'StudyInstanceUID': '',
        'SeriesInstanceUID': '',
        'StudyID': '',
        'SeriesNumber': '',
        'SeriesDate': '',
        'SeriesTime': '',
        'NumberOfSeriesRelatedInstances': '',
        'PatientID': '',
        'OperatorsName': '',
        'AccessionNumber': '',
        'AdmissionID': '',
        'PatientComments': '',
    }

    def __init__(self, options):
        self.scu = scu.SCU(options.get('host'), options.get('port'), options.get('return_port'), options.get('aet'), options.get('aec'))
        super(DicomNetReaper, self).__init__(self.scu.aec, options)
        self.anonymize = options.get('anonymize')
        self.peripheral_data_reapers['gephysio'] = 'gephysio'

    def state_str(self, _id, state):
        return '%s (%s)' % (_id, ', '.join(['%s %s' % (v, k or 'null') for k, v in state.iteritems()]))

    def instrument_query(self):
        i_state = {}
        scu_resp = self.scu.find(scu.SeriesQuery(**self.query_params))
        for r in scu_resp:
            state = {
                'images': int(r['NumberOfSeriesRelatedInstances']),
                '_id': r[self.id_field],
                'opt': r[self.opt_field] if self.opt is not None else None,
            }
            i_state[r['SeriesInstanceUID']] = reaper.ReaperItem(state)
        return i_state or None  # TODO should return None only on communication error

    def reap(self, _id, item, tempdir):
        if item['state']['images'] == 0:
            log.info('ignoring     %s (zero images)', _id)
            return None, {}
        if not self.is_desired_item(item['state']['opt']):
            log.info('ignoring     %s (non-matching opt-%s)', _id, self.opt)
            return None, {}
        reap_start = datetime.datetime.utcnow()
        log.info('reaping      %s', self.state_str(_id, item['state']))
        success, reap_cnt = self.scu.move(scu.SeriesQuery(StudyInstanceUID='', SeriesInstanceUID=_id), tempdir)
        filepaths = [os.path.join(tempdir, filename) for filename in os.listdir(tempdir)]
        log.info('reaped       %s (%d images) in %.1fs', _id, reap_cnt, (datetime.datetime.utcnow() - reap_start).total_seconds())
        if success and reap_cnt > 0:
            dcm = self.DicomFile(filepaths[0], self.id_field, self.opt_field)
            if not self.is_desired_item(dcm.opt):
                log.info('ignoring     %s (non-matching opt-%s)', _id, self.opt)
                return None, {}
        if success and reap_cnt == item['state']['images']:
            acq_map = self.split_into_acquisitions(_id, tempdir, filepaths)
            metadata_map = {}
            for acq_filename, acq_info in acq_map.iteritems():
                self.reap_peripheral_data(tempdir, acq_info['dcm'], acq_info['prefix'], acq_info['log_info'])
                metadata_map[acq_filename] = acq_info['metadata']
            return True, metadata_map
        else:
            return False, {}

    def split_into_acquisitions(self, _id, path, filepaths):
        # pylint: disable=missing-docstring
        dcm_dict = {}
        log.info('inspecting   %s', _id)
        for filepath in filepaths:
            dcm = self.DicomFile(filepath, self.id_field, self.opt_field)
            dcm_dict.setdefault(dcm.acq_no, []).append(filepath)
        log.info('compressing  %s%s', _id, ' (and anonymizing)' if self.anonymize else '')
        acq_map = {}
        for acq_no, acq_paths in dcm_dict.iteritems():
            name_prefix = _id + ('_' + acq_no if acq_no is not None else '')
            dir_name = name_prefix + '_' + 'dicom'
            arcdir_path = os.path.join(path, dir_name)
            os.mkdir(arcdir_path)
            for filepath in acq_paths:
                dcm = self.DicomFile(filepath, self.id_field, self.opt_field, parse=True, anonymize=self.anonymize, timezone=self.timezone)
                filename = os.path.basename(filepath)
                if filename.startswith('(none)'):
                    filename = filename.replace('(none)', 'NA')
                file_time = int(dcm.acquisition_timestamp.strftime('%s'))
                os.utime(filepath, (file_time, file_time))  # correct timestamps
                os.rename(filepath, '%s.dcm' % os.path.join(arcdir_path, filename))
            metadata = self.metadata(dcm)
            arc_path = util.create_archive(arcdir_path, dir_name, metadata)
            shutil.rmtree(arcdir_path)
            acq_map[os.path.basename(arc_path)] = {
                'dcm': dcm,
                'metadata': metadata,
                'prefix': name_prefix,
                'log_info': '%s%s' % (_id, '.' + acq_no if acq_no is not None else ''),
            }
        return acq_map

    class DicomFile(object):

        """
        DicomFile class
        """

        def __init__(self, filepath, id_field, opt_field, parse=False, anonymize=False, timezone=None):
            if not parse and anonymize:
                raise Exception('Cannot anonymize DICOM file without parsing')
            dcm = dicom.read_file(filepath, stop_before_pixels=(not anonymize))
            self._id = dcm.get(id_field, '')
            self.opt = dcm.get(opt_field, '') if opt_field else None
            self.acq_no = str(dcm.get('AcquisitionNumber', '')) or None if dcm.get('Manufacturer').upper() != 'SIEMENS' else None

            if parse:
                series_uid = dcm.get('SeriesInstanceUID')
                if self.is_screenshot(dcm.get('ImageType')):
                    front, back = series_uid.rsplit('.', 1)
                    series_uid = front + '.' + str(int(back) - 1)
                study_datetime = self.timestamp(dcm.get('StudyDate'), dcm.get('StudyTime'), timezone)
                acq_datetime = self.timestamp(dcm.get('AcquisitionDate'), dcm.get('AcquisitionTime'), timezone)
                self.session_uid = dcm.get('StudyInstanceUID')
                self.session_timestamp = study_datetime
                self.subject_firstname, self.subject_lastname = self.parse_patient_name(dcm.get('PatientName', ''))
                self.subject_firstname_hash = hashlib.sha256(self.subject_firstname).hexdigest() if self.subject_firstname else None
                self.subject_lastname_hash = hashlib.sha256(self.subject_lastname).hexdigest() if self.subject_lastname else None
                self.subject_code, self.group__id, self.project_label = parse_id(self._id, 'ex' + dcm.get('StudyID', ''))
                self.acquisition_uid = series_uid + ('_' + str(self.acq_no) if self.acq_no is not None else '')
                self.acquisition_timestamp = acq_datetime or study_datetime
                self.acquisition_label = dcm.get('SeriesDescription')
                self.file_type = FILETYPE

            if parse and anonymize:
                self.subject_firstname = self.subject_lastname = None
                if dcm.get('PatientBirthDate'):
                    dob = self.parse_patient_dob(dcm.PatientBirthDate)
                    if dob:
                        months = 12 * (study_datetime.year - dob.year) + (study_datetime.month - dob.month) - (study_datetime.day < dob.day)
                        dcm.PatientAge = '%03dM' % months if months < 960 else '%03dY' % (months / 12)
                    del dcm.PatientBirthDate
                if dcm.get('PatientName'):
                    del dcm.PatientName
                dcm.save_as(filepath)

        @staticmethod
        def is_screenshot(image_type):
            # pylint: disable=missing-docstring
            if image_type in [GEMS_TYPE_SCREENSHOT, GEMS_TYPE_VXTL]:
                return True
            return False

        @staticmethod
        def timestamp(date, time, timezone):
            # pylint: disable=missing-docstring
            if date and time:
                return util.localize_timestamp(datetime.datetime.strptime(date + time[:6], '%Y%m%d%H%M%S'), timezone)
            return None

        @staticmethod
        def parse_patient_name(name):
            """
            Parse patient name.

            expects "lastname" + "delimiter" + "firstname".

            Parameters
            ----------
            name : str
                string of subject first and last name, delimited by a '^' or ' '

            Returns
            -------
            firstname : str
                first name parsed from name
            lastname : str
                last name parsed from name

            """
            if '^' in name:
                lastname, _, firstname = name.partition('^')
            else:
                firstname, _, lastname = name.rpartition(' ')
            return firstname.strip().title(), lastname.strip().title()

        @staticmethod
        def parse_patient_dob(dob):
            """
            Parse date string and sanity check.

            expects date string in YYYYMMDD format

            Parameters
            ----------
            dob : str
                dob as string YYYYMMDD

            Returns
            -------
            dob : datetime object

            """
            try:
                dob = datetime.datetime.strptime(dob, '%Y%m%d')
                if dob < datetime.datetime(1900, 1, 1):
                    raise ValueError
            except (ValueError, TypeError):
                dob = None
            return dob


def update_arg_parser(ap):
    # pylint: disable=missing-docstring
    ap.add_argument('host', help='remote hostname or IP')
    ap.add_argument('port', help='remote port')
    ap.add_argument('return_port', help='local return port')
    ap.add_argument('aet', help='local AE title')
    ap.add_argument('aec', help='remote AE title')

    ap.add_argument('-A', '--no-anonymize', dest='anonymize', action='store_false', help='do not anonymize patient name and birthdate')

    return ap


def main():
    # pylint: disable=missing-docstring
    reaper.main(DicomNetReaper, update_arg_parser)
