""" SciTran Orthanc DICOM Reaper """

import logging
import requests

from . import dicom_reaper

log = logging.getLogger('reaper.orthanc')


class OrthancReaper(dicom_reaper.DicomReaper):

    """OrthancReaper class"""

    def __init__(self, options):
        super(OrthancReaper, self).__init__(options)
        self.orthanc_host = options.get('orthanc_host')

    def before_reap(self, _id):
        """
        Orthanc halt incoming stores
        """
        disable_function = """ function ReceivedInstanceFilter(dicom, origin)
                               error("All Stores Rejected")
                               end """
        with requests.Session() as rs:
            exec_script_resp = rs.post('http://{0}/tools/execute-script'.format(self.orthanc_host), data=disable_function)
            exec_script_resp.raise_for_status()

    def after_reap_success(self, _id):
        """
        Orthanc delete study
        """
        with requests.Session() as rs:
            log.info(_id)
            lookup_resp = rs.post('http://{0}/tools/lookup'.format(self.orthanc_host), data=_id)
            lookup_resp.raise_for_status()
            response_obj = lookup_resp.json()
            log.info(response_obj)
            if len(response_obj) != 1:
                raise Exception("Unexpected state: More than 1 series with same UID")
            log.info(response_obj[0]['ID'])

            delete_resp = rs.delete('http://{0}/series/{1}'.format(self.orthanc_host, response_obj[0]['ID']))
            delete_resp.raise_for_status()

    def after_reap(self, _id):
        """
        Orthanc allow incoming stores
        """
        enable_function = """ function ReceivedInstanceFilter(dicom, origin)
                               return true
                               end """
        with requests.Session() as rs:
            exec_script_resp = rs.post('http://{0}/tools/execute-script'.format(self.orthanc_host), data=enable_function)
            exec_script_resp.raise_for_status()


def update_arg_parser(ap):
    # pylint: disable=missing-docstring
    ap = dicom_reaper.update_arg_parser(ap)
    ap.add_argument('orthanc_host', help='Orthanc hostname and port')
    return ap


def main(cls=OrthancReaper, arg_parser_update=update_arg_parser):
    # pylint: disable=missing-docstring
    dicom_reaper.main(cls, arg_parser_update)
