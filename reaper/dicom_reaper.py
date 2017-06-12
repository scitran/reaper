""" SciTran DICOM Net Reaper """

import os
import logging
import datetime

from . import dcm
from . import scu
from . import reaper

log = logging.getLogger('reaper.dicom')


class DicomReaper(reaper.Reaper):

    """DicomReaper class"""

    def __init__(self, options):
        self.scu = scu.SCU(options.get('host'), options.get('port'), options.get('return_port'), options.get('aet'), options.get('aec'))
        super(DicomReaper, self).__init__(self.scu.aec, options)
        self.de_identify = options.get('de_identify')

        self.query_tags = {self.map_key: ''}
        if self.opt_key is not None:
            self.query_tags[self.opt_key] = ''

    def state_str(self, _id, state=None):
        if state:
            return _id + ', ' + ', '.join(['%s %s' % (v, k or 'null') for k, v in state.iteritems()])
        else:
            return _id

    def instrument_query(self):
        i_state = {}
        scu_studies = None
        scu_series = self.scu.find(scu.SeriesQuery(**scu.SCUQuery(**self.query_tags)))
        if scu_series is None:
            return None
        for series in scu_series:
            if not series['NumberOfSeriesRelatedInstances']:
                scu_images = self.scu.find(scu.ImageQuery(**scu.SCUQuery(SeriesInstanceUID=series.SeriesInstanceUID)))
                if scu_images is None:
                    return None
                series['NumberOfSeriesRelatedInstances'] = len(scu_images)
            if self.opt and series[self.opt_key] is None:
                if scu_studies is None:
                    scu_studies = self.scu.find(scu.StudyQuery(**scu.SCUQuery(**self.query_tags)))
                    if scu_studies is None:
                        return None
                    scu_studies = {study.StudyInstanceUID: study for study in scu_studies}
                series[self.opt_key] = scu_studies.get(series.StudyInstanceUID, {}).get(self.opt_key)
            state = {
                'images': int(series['NumberOfSeriesRelatedInstances']),
                '_id': series[self.map_key],
                'opt': series[self.opt_key] if self.opt is not None else None,
            }
            i_state[series['SeriesInstanceUID']] = reaper.ReaperItem(state)
        return i_state

    def reap(self, _id, item, tempdir):
        if item['state']['images'] == 0:
            log.warning('Ignoring     %s (zero images)', _id)
            return None, {}
        if not self.is_desired_item(item['state']['opt']):
            log.warning('Ignoring     %s (non-matching opt-%s)', _id, self.opt)
            return None, {}
        reapdir = os.path.join(tempdir, 'raw_dicoms')
        os.mkdir(reapdir)
        log.warning('Reaping      %s', self.state_str(_id, item['state']))
        start = datetime.datetime.utcnow()
        success, reap_cnt = self.scu.move(scu.SeriesQuery(SeriesInstanceUID=_id), reapdir)
        duration = (datetime.datetime.utcnow() - start).total_seconds()
        log.info('Reaped       %s, %d images in %.1fs [%.0f/s]', _id, reap_cnt, duration, reap_cnt / duration)
        if success and reap_cnt > 0:
            df = dcm.DicomFile(os.path.join(reapdir, os.listdir(reapdir)[0]), self.map_key, self.opt_key)
            if not self.is_desired_item(df.opt):
                log.warning('Ignoring     %s (non-matching opt-%s)', _id, self.opt)
                return None, {}
        if success and reap_cnt == item['state']['images']:
            log.warning('Processing   %s', self.state_str(_id))
            metadata_map = dcm.pkg_series(_id, reapdir, self.map_key, self.opt_key, self.de_identify, self.timezone)
            return True, metadata_map
        else:
            return False, {}


def update_arg_parser(ap):
    # pylint: disable=missing-docstring
    ap.add_argument('host', help='remote hostname or IP')
    ap.add_argument('port', help='remote port')
    ap.add_argument('return_port', help='local return port')
    ap.add_argument('aet', help='local AE title')
    ap.add_argument('aec', help='remote AE title')

    ap.add_argument('--de-identify', action='store_true', help='de-identify data before upload')

    return ap


def main(cls=DicomReaper, arg_parser_update=update_arg_parser):
    # pylint: disable=missing-docstring
    reaper.main(cls, arg_parser_update)
