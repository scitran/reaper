""" SciTran DICOM Net Reaper """

import os
import logging
import datetime
import re
import zipfile

from . import dcm
from . import scu
from . import reaper
from subprocess import Popen, PIPE, STDOUT

log = logging.getLogger('reaper.dicom')


class DicomReaper(reaper.Reaper):

    """DicomReaper class"""

    def __init__(self, options):
        self.scu = scu.SCU(options.get('host'), options.get('port'), options.get('return_port'), options.get('aet'), options.get('aec'))
        super(DicomReaper, self).__init__(self.scu.aec, options)
        self.anonymize = options.get('anonymize')
        self.uid_ext_command = options.get('uid_ext_command')

        self.query_tags = {self.map_key: ''}
        if self.opt_key is not None:
            self.query_tags[self.opt_key] = ''

    def state_str(self, _id, state):
        return '%s (%s)' % (_id, ', '.join(['%s %s' % (v, k or 'null') for k, v in state.iteritems()]))

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
            log.info('ignoring     %s (zero images)', _id)
            return None, {}
        if not self.is_desired_item(item['state']['opt']):
            log.info('ignoring     %s (non-matching opt-%s)', _id, self.opt)
            return None, {}
        reapdir = os.path.join(tempdir, 'raw_dicoms')
        os.mkdir(reapdir)
        reap_start = datetime.datetime.utcnow()
        log.info('reaping      %s', self.state_str(_id, item['state']))
        success, reap_cnt = self.scu.move(scu.SeriesQuery(SeriesInstanceUID=_id), reapdir)
        log.info('reaped       %s (%d images) in %.1fs', _id, reap_cnt, (datetime.datetime.utcnow() - reap_start).total_seconds())
        if success and reap_cnt > 0:
            df = dcm.DicomFile(os.path.join(reapdir, os.listdir(reapdir)[0]), self.map_key, self.opt_key)
            if not self.is_desired_item(df.opt):
                log.info('ignoring     %s (non-matching opt-%s)', _id, self.opt)
                return None, {}
        if success and reap_cnt == item['state']['images']:
            metadata_map = dcm.pkg_series(_id, reapdir, self.map_key, self.opt_key, self.anonymize, self.timezone)
            self._custom_acq_uid(metadata_map)
            return True, metadata_map
        else:
            return False, {}

    def _custom_acq_uid(self, metadata_map):
        if self.uid_ext_command is None:
            return
        for filepath, metadata in metadata_map.iteritems():
            print(filepath)
            print(metadata)
            dcm_dir = re.sub('\.zip$','',filepath)

            unzipped_file = [os.path.join(dcm_dir, filename) for filename in os.listdir(dcm_dir)][0]

            formatted_string = self.uid_ext_command.format(unzipped_file)
            print(formatted_string)


            arg_list = formatted_string.split()

            p = Popen(arg_list,
                       stdout=PIPE,
                       stderr=STDOUT)
            out, _ = p.communicate()

            if p.returncode and p.returncode != 0:
                log.error('Error with command. Return code = {0}'.format(p.returncode))
                raise RuntimeError(out)
            print(out.rstrip())
            metadata['acquisition']['uid'] = out.rstrip()
            print(metadata)



def update_arg_parser(ap):
    # pylint: disable=missing-docstring
    ap.add_argument('host', help='remote hostname or IP')
    ap.add_argument('port', help='remote port')
    ap.add_argument('return_port', help='local return port')
    ap.add_argument('aet', help='local AE title')
    ap.add_argument('aec', help='remote AE title')

    ap.add_argument('-A', '--no-anonymize', dest='anonymize', action='store_false', help='do not anonymize patient name and birthdate')
    ap.add_argument('--uid-ext-command', dest='uid_ext_command', help='Command to execute against single source file to generate acquisition uid', default=None)

    return ap


def main(cls=DicomReaper, arg_parser_update=update_arg_parser):
    # pylint: disable=missing-docstring
    reaper.main(cls, arg_parser_update)
