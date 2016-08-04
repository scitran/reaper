""" SciTran Orthanc DICOM Reaper """

import logging
import requests

from . import dicom_reaper

log = logging.getLogger('reaper.orthanc')


class OrthancReaper(dicom_reaper.DicomReaper):

    """OrthancReaper class"""

    rs = requests.Session()

    def __init__(self, options):
        super(OrthancReaper, self).__init__(options)
        self.orthanc_uri = options.get('orthanc_uri').strip('/')

    def before_reap(self, _id):
        """
        Orthanc halt incoming stores
        """
        disable_function = """ function ReceivedInstanceFilter(dicom, origin)
                               error("All Stores Rejected")
                               end """
        r = self.rs.post(self.orthanc_uri + '/tools/execute-script', data=disable_function)
        r.raise_for_status()

    def after_reap_success(self, _id):
        """
        Orthanc delete study
        """
        log.info(_id)
        r = self.rs.post(self.orthanc_uri + '/tools/lookup', data=_id)
        r.raise_for_status()
        payload = r.json()
        log.info(payload)
        if len(payload) != 1:
            raise Exception("Unexpected state: More than 1 series with same UID")
        log.info(payload[0]['ID'])

        r = self.rs.delete(self.orthanc_uri + '/series/' + payload[0]['ID'])
        r.raise_for_status()

    def after_reap(self, _id):
        """
        Orthanc allow incoming stores
        """
        enable_function = """ function ReceivedInstanceFilter(dicom, origin)
                               return true
                               end """
        r = self.rs.post(self.orthanc_uri + '/tools/execute-script', data=enable_function)
        r.raise_for_status()


def update_arg_parser(ap):
    # pylint: disable=missing-docstring
    ap = dicom_reaper.update_arg_parser(ap)
    ap.add_argument('orthanc_uri', help='Orthanc base URI')
    return ap


def main(cls=OrthancReaper, arg_parser_update=update_arg_parser):
    # pylint: disable=missing-docstring
    dicom_reaper.main(cls, arg_parser_update)
