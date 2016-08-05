""" SciTran Orthanc DICOM Reaper """

import logging
import requests

from . import dicom_reaper

log = logging.getLogger('reaper.orthanc')


class OrthancReaper(dicom_reaper.DicomReaper):

    """OrthancReaper class"""

    def __init__(self, options):
        super(OrthancReaper, self).__init__(options)
        self.orthanc_uri = options.get('orthanc_uri').strip('/')

    def before_run(self):
        """
        Operations for before the run loop.
        """
        self._enable_orthanc()

    def before_reap(self, _id):
        """
        Operations for before the series is reaped.
        """
        self._disable_orthanc(_id)

    def after_reap_success(self, _id):
        """
        Operations after the series is reaped successfully.
        """
        self._delete_series(_id)

    def after_reap(self, _id):
        """
        Operations after the series is reaped, regardless of result.
        """
        self._enable_orthanc()

    def _enable_orthanc(self):
        """
        Orthanc allow all incoming stores
        """
        enable_function = """ function ReceivedInstanceFilter(dicom, origin)
                                  return true
                              end """
        r = requests.post(self.orthanc_uri + '/tools/execute-script', data=enable_function)
        r.raise_for_status()
        log.debug("Orthanc Stores enabled for all series.")

    def _disable_orthanc(self, _id):
        """
        Orthanc halt incoming stores for DICOM Series being reaped.
        """
        disable_function = """ function ReceivedInstanceFilter(dicom, origin)
                                   blocking_series_uid = "{0}"
                                   if dicom.SeriesInstanceUID == blocking_series_uid then
                                       error("Stores blocked for SeriesInstanceUID " .. blocking_series_uid)
                                   end
                                   return true

                               end """.format(_id)
        r = requests.post(self.orthanc_uri + '/tools/execute-script', data=disable_function)
        r.raise_for_status()
        log.debug("Orthanc Stores disabled for SeriesInstanceUID %s", _id)

    def _delete_series(self, _id):
        """
        Orthanc delete DICOM Series
        """
        log.debug("Requesting Orthanc ID for SeriesInstanceUID %s", _id)
        r = requests.post(self.orthanc_uri + '/tools/lookup', data=_id)
        r.raise_for_status()
        payload = r.json()
        if len(payload) != 1:
            raise Exception("Unexpected state: More than 1 series with same UID")
        log.debug("About to delete Orthanc ID %s", payload[0]['ID'])

        r = requests.delete(self.orthanc_uri + '/series/' + payload[0]['ID'])
        r.raise_for_status()
        log.debug("Successfully deleted SeriesInstanceUID %s", _id)


def update_arg_parser(ap):
    # pylint: disable=missing-docstring
    ap = dicom_reaper.update_arg_parser(ap)
    ap.add_argument('orthanc_uri', help='Orthanc base URI')
    return ap


def main(cls=OrthancReaper, arg_parser_update=update_arg_parser):
    # pylint: disable=missing-docstring
    dicom_reaper.main(cls, arg_parser_update)
