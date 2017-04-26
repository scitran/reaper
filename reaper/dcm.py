"""SciTran Reaper DICOM utility functions"""

import os
import shutil
import hashlib
import logging
import datetime

import dicom

from . import util

log = logging.getLogger(__name__)

FILETYPE = 'dicom'
GEMS_TYPE_SCREENSHOT = ['DERIVED', 'SECONDARY', 'SCREEN SAVE']
GEMS_TYPE_VXTL = ['DERIVED', 'SECONDARY', 'VXTL STATE']


def pkg_series(_id, path, map_key, opt_key=None, de_identify=False, timezone=None):
    # pylint: disable=missing-docstring
    dcm_dict = {}
    log.debug('Inspecting   %s', _id)
    start = datetime.datetime.utcnow()
    filepaths = [os.path.join(path, filename) for filename in os.listdir(path)]
    file_cnt = len(filepaths)
    for filepath in filepaths:
        dcm = DicomFile(filepath, map_key, opt_key)
        dcm_dict.setdefault(dcm.acq_no, []).append(filepath)
    duration = (datetime.datetime.utcnow() - start).total_seconds()
    log.info('Inspected    %s, %d images in %.1fs [%.0f/s]', _id, file_cnt, duration, file_cnt / duration)
    log.debug('Compressing  %s%s', _id, ' (and anonymizing)' if de_identify else '')
    metadata_map = {}
    start = datetime.datetime.utcnow()
    for acq_no, acq_paths in dcm_dict.iteritems():
        name_prefix = _id + ('_' + acq_no if acq_no is not None else '')
        dir_name = name_prefix + '.' + FILETYPE
        arcdir_path = os.path.join(path, '..', dir_name)
        os.mkdir(arcdir_path)
        for filepath in acq_paths:
            dcm = DicomFile(filepath, map_key, opt_key, parse=True, de_identify=de_identify, timezone=timezone)
            filename = os.path.basename(filepath)
            if filename.startswith('(none)'):
                filename = filename.replace('(none)', 'NA')
            file_time = max(int(dcm.acquisition_timestamp.strftime('%s')), 315561600)  # zip can't handle < 1980
            os.utime(filepath, (file_time, file_time))  # correct timestamps
            os.rename(filepath, '%s.dcm' % os.path.join(arcdir_path, filename))
        arc_path = util.create_archive(arcdir_path, dir_name)
        metadata = util.object_metadata(dcm, timezone, os.path.basename(arc_path))
        util.set_archive_metadata(arc_path, metadata)
        shutil.rmtree(arcdir_path)
        metadata_map[arc_path] = metadata
    duration = (datetime.datetime.utcnow() - start).total_seconds()
    log.info('Compressed   %s%s, %d images in %.1fs [%.0f/s]',
             _id, ' (and anonymized)' if de_identify else '', file_cnt, duration, file_cnt / duration)
    return metadata_map


class DicomFileError(dicom.errors.InvalidDicomError):
    """DicomFileError class"""
    pass


class DicomFile(object):

    """
    DicomFile class
    """

    # pylint: disable=too-few-public-methods

    def __init__(self, filepath, map_key=None, opt_key=None, parse=False, de_identify=False, timezone=None):
        try:
            self.raw = dcm = dicom.read_file(filepath, stop_before_pixels=(not de_identify))
        except dicom.errors.InvalidDicomError:
            raise DicomFileError()

        self._id = dcm.get(map_key, '') if opt_key else None
        self.opt = dcm.get(opt_key, '') if opt_key else None
        self.acq_no = str(dcm.get('AcquisitionNumber', '')) or None if dcm.get('Manufacturer').upper() != 'SIEMENS' else None

        if parse or de_identify:
            series_uid = dcm.get('SeriesInstanceUID')
            if self.__is_screenshot(dcm.get('ImageType')):
                front, back = series_uid.rsplit('.', 1)
                series_uid = front + '.' + str(int(back) - 1)
            study_datetime = self.__timestamp(dcm.get('StudyDate'), dcm.get('StudyTime'), timezone)
            acq_datetime = self.__timestamp(dcm.get('AcquisitionDate'), dcm.get('AcquisitionTime'), timezone)
            self.session_uid = dcm.get('StudyInstanceUID')
            self.session_timestamp = study_datetime
            self.subject_firstname, self.subject_lastname = self.__parse_patient_name(dcm.get('PatientName', ''))
            self.subject_firstname_hash = hashlib.sha256(self.subject_firstname).hexdigest() if self.subject_firstname else None
            self.subject_lastname_hash = hashlib.sha256(self.subject_lastname).hexdigest() if self.subject_lastname else None
            self.subject_code, self.group__id, self.project_label = util.parse_sorting_info(self._id, 'ex' + dcm.get('StudyID', ''))
            self.acquisition_uid = series_uid + ('_' + str(self.acq_no) if self.acq_no is not None else '')
            self.acquisition_timestamp = acq_datetime or study_datetime
            self.acquisition_label = dcm.get('SeriesDescription')
            self.file_type = FILETYPE

        if de_identify:
            self.subject_firstname = self.subject_lastname = None
            if dcm.get('PatientBirthDate'):
                dob = self.__parse_patient_dob(dcm.PatientBirthDate)
                if dob:
                    months = 12 * (study_datetime.year - dob.year) + (study_datetime.month - dob.month) - (study_datetime.day < dob.day)
                    dcm.PatientAge = '%03dM' % months if months < 960 else '%03dY' % (months / 12)
            dcm.pop('PatientBirthDate', None)
            dcm.pop('PatientName', None)
            dcm.pop('PatientID', None)
            dcm.save_as(filepath)

    def get_tag(self, tag_name, default=None):
        # pylint: disable=missing-docstring
        if tag_name:
            return str(self.raw.get(tag_name)).strip('\x00') or default
        return default

    @staticmethod
    def __is_screenshot(image_type):
        # pylint: disable=missing-docstring
        if image_type in [GEMS_TYPE_SCREENSHOT, GEMS_TYPE_VXTL]:
            return True
        return False

    @staticmethod
    def __timestamp(date, time, timezone):
        # pylint: disable=missing-docstring
        if date and time and timezone:
            return util.localize_timestamp(datetime.datetime.strptime(date + time[:6], '%Y%m%d%H%M%S'), timezone)
        return None

    @staticmethod
    def __parse_patient_name(name):
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
    def __parse_patient_dob(dob):
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
