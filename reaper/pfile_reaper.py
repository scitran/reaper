""" SciTran P-File Reaper """

# TODO:
#   - make aux files part of state
#   - include add pfiles on one uid in state
#   - add custom state comparision function that does not re-reap when pfiles start to be overwritten

import os
import sys
import glob
import gzip
import shutil
import struct
import logging
import datetime

from . import util
from . import reaper
from . import dicom_net_reaper

log = logging.getLogger('reaper.pfile')

FILETYPE = 'pfile'


class PFileReaper(reaper.Reaper):

    """PFileReaper class"""

    def __init__(self, options):
        if not os.path.isdir(options.get('path')):
            log.error('path argument must be a directory')
            sys.exit(1)
        self.data_glob = os.path.join(options.get('path'), 'P?????.7')
        super(PFileReaper, self).__init__(options.get('path').strip('/').replace('/', '_'), options)
        self.reap_auxfiles = options['aux']
        # self.peripheral_data_reapers['gephysio'] = gephysio.reap

    def state_str(self, _id, state):
        return '%s, [%s, %s]' % (_id, state['mod_time'].strftime(reaper.DATE_FORMAT), util.hrsize(state['size']))

    def instrument_query(self):
        i_state = {}
        try:
            filepaths = glob.glob(self.data_glob)
            if not filepaths:
                raise Warning('no matching files found (or error while checking for files)')
        except (OSError, Warning) as ex:
            filepaths = []
            log.warning(ex)
        for fp in filepaths:
            stats = os.stat(fp)
            state = {
                'mod_time': datetime.datetime.utcfromtimestamp(stats.st_mtime),
                'size': stats.st_size,
            }
            i_state[os.path.basename(fp)] = reaper.ReaperItem(state, path=fp)
        return i_state

    def reap(self, _id, item, tempdir):
        try:
            pf = PFile(item['path'], self.id_field, self.opt_field)
        except IOError:
            log.warning('skipping     %s (disappeared or unparsable)', _id)
            return None, {}
        if self.is_desired_item(pf.opt):
            if self.reap_auxfiles:
                success, metadata = self.reap_aux(_id, item, pf, tempdir)
            else:
                success, metadata = self.reap_one(_id, item, pf, tempdir)
        else:
            log.info('ignoring     %s (non-matching opt-%s)', _id, self.opt)
            success, metadata = None, {}
        return success, metadata

    def reap_one(self, _id, item, pf, tempdir):
        # pylint: disable=missing-docstring
        pfile_size = util.hrsize(item['state']['size'])
        log.info('reaping.gz   %s [%s%s]', _id, pfile_size, '')
        filepath = os.path.join(tempdir, os.path.basename(item['path']) + '.gz')
        try:
            with open(item['path'], 'rb') as fd, gzip.open(filepath, 'wb') as fd_gz:
                shutil.copyfileobj(fd, fd_gz, 2**30)
        # pylint: disable=broad-except
        except Exception:
            return False, None
        else:
            return True, {os.path.basename(filepath): self.metadata(pf)}

    def reap_aux(self, _id, item, pf, tempdir):
        # pylint: disable=missing-docstring
        uid_infix = '_' + pf.series_uid + '_'
        auxpaths = glob.glob(os.path.join(os.path.dirname(item['path']), '*' + uid_infix + '*'))
        auxfiles = [(ap, os.path.basename(ap).replace(uid_infix, '_')) for ap in auxpaths]
        log.debug('staging      %s%s', _id, ', ' + ', '.join([af[1] for af in auxfiles]) if auxfiles else '')

        reap_path = os.path.join(tempdir, pf.acquisition_uid + '_' + FILETYPE)
        os.mkdir(reap_path)

        os.symlink(item['path'], os.path.join(reap_path, os.path.basename(item['path'])))
        for ap, an in auxfiles:
            os.symlink(ap, os.path.join(reap_path, an))

        pfile_size = util.hrsize(item['state']['size'])
        reap_start = datetime.datetime.utcnow()
        auxfile_log_str = ' + %d aux files' % len(auxfiles) if auxfiles else ''
        log.info('reaping.zip  %s [%s%s]', _id, pfile_size, auxfile_log_str)
        metadata = self.metadata(pf)
        try:
            filepath = util.create_archive(reap_path, os.path.basename(reap_path), metadata)
            shutil.rmtree(reap_path)
        # pylint: disable=broad-except
        except Exception:
            log.warning('reap error   %s%s', _id, ' or aux files' if auxfiles else '')
            return False, None
        else:
            reap_time = (datetime.datetime.utcnow() - reap_start).total_seconds()
            log.info('reaped.zip   %s [%s%s] in %.1fs', _id, pfile_size, auxfile_log_str, reap_time)
            self.reap_peripheral_data(tempdir, pf, pf.acquisition_uid, _id)
            return True, {os.path.basename(filepath): metadata}


class PFile(object):

    """PFile class"""

    # pylint: disable=too-few-public-methods

    def __init__(self, filepath, id_field, opt_field):
        pf = _RawPFile(filepath)

        if id_field == 'PatientID':
            self._id = pf.patient_id
        else:
            self._id = None

        if opt_field == 'AccessionNumber':
            self.opt = pf.accession_no
        else:
            self.opt = None

        self.session_uid = pf.exam_uid
        self.series_uid = pf.series_uid
        self.acquisition_uid = pf.series_uid + '_' + str(pf.acq_no)
        self.acquisition_timestamp = pf.timestamp
        self.acquisition_label = pf.series_desc
        self.subj_code, self.group__id, self.project_label = dicom_net_reaper.parse_id(self._id, 'ex' + pf.exam_no)
        self.file_type = FILETYPE


class _RawPFileError(Exception):
    pass


class _RawPFile(object):

    """_RawPFile class"""

    # pylint: disable=too-few-public-methods

    def __init__(self, filepath):
        # pylint: disable=multiple-statements,too-many-statements
        fd = open(filepath, 'rb')

        version_bytes = fd.read(4)

        fd.seek(34); logo = (struct.unpack("10s", fd.read(struct.calcsize("10s")))[0]).split('\0', 1)[0]
        if logo != 'GE_MED_NMR' and logo != 'INVALIDNMR':
            raise _RawPFileError(fd.name + ' is not a valid PFile')

        fd.seek(16); scan_date = str(struct.unpack("10s", fd.read(struct.calcsize("10s")))[0])
        fd.seek(26); scan_time = str(struct.unpack("8s", fd.read(struct.calcsize("8s")))[0])

        if version_bytes == '\x00\x00\xc0A':    # v24
            fd.seek(143516); self.exam_no = str(struct.unpack("H", fd.read(struct.calcsize("H")))[0])
            fd.seek(144248); self.exam_uid = self.unpack_uid(struct.unpack("32s", fd.read(struct.calcsize("32s")))[0])
            fd.seek(144409); self.patient_id = (struct.unpack("65s", fd.read(struct.calcsize("65s")))[0]).split('\0', 1)[0]
            fd.seek(144474); self.accession_no = (struct.unpack("17s", fd.read(struct.calcsize("17s")))[0]).split('\0', 1)[0]
            fd.seek(145622); self.series_no = struct.unpack("h", fd.read(struct.calcsize("h")))[0]
            fd.seek(145762); self.series_desc = (struct.unpack("65s", fd.read(struct.calcsize("65s")))[0]).split('\0', 1)[0]
            fd.seek(145875); self.series_uid = self.unpack_uid(struct.unpack("32s", fd.read(struct.calcsize("32s")))[0])
            fd.seek(148388); im_datetime = struct.unpack("i", fd.read(struct.calcsize("i")))[0]
            fd.seek(148834); self.acq_no = struct.unpack("h", fd.read(struct.calcsize("h")))[0]

        elif version_bytes == 'V\x0e\xa0A':     # v23
            fd.seek(143516); self.exam_no = str(struct.unpack("H", fd.read(struct.calcsize("H")))[0])
            fd.seek(144248); self.exam_uid = self.unpack_uid(struct.unpack("32s", fd.read(struct.calcsize("32s")))[0])
            fd.seek(144409); self.patient_id = (struct.unpack("65s", fd.read(struct.calcsize("65s")))[0]).split('\0', 1)[0]
            fd.seek(144474); self.accession_no = (struct.unpack("17s", fd.read(struct.calcsize("17s")))[0]).split('\0', 1)[0]
            fd.seek(145622); self.series_no = struct.unpack("h", fd.read(struct.calcsize("h")))[0]
            fd.seek(145762); self.series_desc = (struct.unpack("65s", fd.read(struct.calcsize("65s")))[0]).split('\0', 1)[0]
            fd.seek(145875); self.series_uid = self.unpack_uid(struct.unpack("32s", fd.read(struct.calcsize("32s")))[0])
            fd.seek(148388); im_datetime = struct.unpack("i", fd.read(struct.calcsize("i")))[0]
            fd.seek(148834); self.acq_no = struct.unpack("h", fd.read(struct.calcsize("h")))[0]

        elif version_bytes == 'J\x0c\xa0A':     # v22
            fd.seek(143516); self.exam_no = str(struct.unpack("H", fd.read(struct.calcsize("H")))[0])
            fd.seek(144240); self.exam_uid = self.unpack_uid(struct.unpack("32s", fd.read(struct.calcsize("32s")))[0])
            fd.seek(144401); self.patient_id = (struct.unpack("65s", fd.read(struct.calcsize("65s")))[0]).split('\0', 1)[0]
            fd.seek(144466); self.accession_no = (struct.unpack("17s", fd.read(struct.calcsize("17s")))[0]).split('\0', 1)[0]
            fd.seek(145622); self.series_no = struct.unpack("h", fd.read(struct.calcsize("h")))[0]
            fd.seek(145762); self.series_desc = (struct.unpack("65s", fd.read(struct.calcsize("65s")))[0]).split('\0', 1)[0]
            fd.seek(145875); self.series_uid = self.unpack_uid(struct.unpack("32s", fd.read(struct.calcsize("32s")))[0])
            fd.seek(148388); im_datetime = struct.unpack("i", fd.read(struct.calcsize("i")))[0]
            fd.seek(148834); self.acq_no = struct.unpack("h", fd.read(struct.calcsize("h")))[0]

        elif version_bytes == '\x00\x000A':     # v12
            fd.seek(61576); self.exam_no = str(struct.unpack("H", fd.read(struct.calcsize("H")))[0])
            fd.seek(61966); self.exam_uid = self.unpack_uid(struct.unpack("32s", fd.read(struct.calcsize("32s")))[0])
            fd.seek(62127); self.patient_id = (struct.unpack("65s", fd.read(struct.calcsize("65s")))[0]).split('\0', 1)[0]
            fd.seek(62192); self.accession_no = (struct.unpack("17s", fd.read(struct.calcsize("17s")))[0]).split('\0', 1)[0]
            fd.seek(62710); self.series_no = struct.unpack("h", fd.read(struct.calcsize("h")))[0]
            fd.seek(62786); self.series_desc = (struct.unpack("65s", fd.read(struct.calcsize("65s")))[0]).split('\0', 1)[0]
            fd.seek(62899); self.series_uid = self.unpack_uid(struct.unpack("32s", fd.read(struct.calcsize("32s")))[0])
            fd.seek(65016); im_datetime = struct.unpack("i", fd.read(struct.calcsize("i")))[0]
            fd.seek(65328); self.acq_no = struct.unpack("h", fd.read(struct.calcsize("h")))[0]

        else:
            raise _RawPFileError(fd.name + ' is not a valid PFile or of an unsupported version')

        if im_datetime > 0:
            self.timestamp = datetime.datetime.utcfromtimestamp(im_datetime)
        else:
            month, day, year = [int(i) for i in scan_date.split('\0', 1)[0].split('/')]
            hour, minute = [int(i) for i in scan_time.split('\0', 1)[0].split(':')]
            self.timestamp = datetime.datetime(year + 1900, month, day, hour, minute)  # GE's epoch begins in 1900

        fd.close()

    @staticmethod
    def unpack_uid(uid):
        # pylint: disable=missing-docstring
        return ''.join([str(i - 1) if i < 11 else '.' for pair in [(ord(c) >> 4, ord(c) & 15) for c in uid] for i in pair if i > 0])


def update_arg_parser(ap):
    # pylint: disable=missing-docstring
    ap.add_argument('path', help='path to PFiles')
    ap.add_argument('--aux', action='store_true', help='include auxiliary files')

    return ap


def main():
    # pylint: disable=missing-docstring
    reaper.main(PFileReaper, update_arg_parser)
