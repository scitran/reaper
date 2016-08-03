""" SciTran Orthanc Net Reaper """

import os
import logging
import datetime
import requests


from . import dcm
from . import scu
from . import reaper
from . import dicom_reaper

log = logging.getLogger('reaper.dicom')


class OrthancNetReaper(dicom_reaper.DicomNetReaper):

    """OrthancNetReaper class"""

    def __init__(self, options):
        super(OrthancNetReaper, self).__init__(options)
        self.remote_host = options.get('host')

    def before_reap(self, _id):
        """
        Orthanc halt incoming stores
        """
        disable_function = """ function ReceivedInstanceFilter(dicom, origin)
                               error("All Stores Rejected")
                               end """
        with requests.Session() as rs:
            exec_script_resp = rs.post('http://{0}:8104/tools/execute-script'.format(self.remote_host), data=disable_function)
            exec_script_resp.raise_for_status()

    def after_reap_success(self, _id):
        """
        Orthanc delete study
        """
        with requests.Session() as rs:
            log.info(_id)
            lookup_resp = rs.post('http://{0}:8104/tools/lookup'.format(self.remote_host), data=_id)
            lookup_resp.raise_for_status()
            response_obj = lookup_resp.json()
            log.info(response_obj)
            if len(response_obj) != 1:
                raise Exception("Unexpected state: More than 1 series with same UID")
            log.info(response_obj[0]['ID'])

            delete_resp = rs.delete('http://{0}:8104/series/{1}'.format(self.remote_host, response_obj[0]['ID']))
            lookup_resp.raise_for_status()

    def after_reap(self, _id):
        """
        Orthanc allow incoming stores
        """
        enable_function = """ function ReceivedInstanceFilter(dicom, origin)
                               return true
                               end """
        with requests.Session() as rs:
            exec_script_resp = rs.post('http://{0}:8104/tools/execute-script'.format(self.remote_host), data=enable_function)
            exec_script_resp.raise_for_status()


def main():
    # pylint: disable=missing-docstring
    reaper.main(OrthancNetReaper, dicom_reaper.update_arg_parser)
