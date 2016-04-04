# @author:  Gunnar Schaefer

import logging
logging.basicConfig(
        format='%(asctime)s %(name)16.16s:%(levelname)4.4s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        )
log = logging.getLogger('reaper')
logging.getLogger('requests').setLevel(logging.WARNING)

import os
import re
import sys
import json
import pytz
import time
import tzlocal
import datetime
import requests
import requests_toolbelt

from . import util
from . import tempdir as tempfile

SLEEPTIME = 60
GRACEPERIOD = 86400
OFFDUTY_SLEEPTIME = 300
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


METADATA = [
    # required
    ('group', '_id'),
    ('project', 'label'),
    ('session', 'uid'),
    ('acquisition', 'uid'),
    # desired (for enhanced UI/UX)
    ('session', 'timestamp'),
    ('session', 'timezone'),        # auto-set
    ('subject', 'code'),
    ('acquisition', 'label'),
    ('acquisition', 'timestamp'),
    ('acquisition', 'timezone'),    # auto-set
    ('file', 'type'),
    # optional
    ('session', 'label'),
    ('session', 'operator'),
    ('subject', 'firstname'),
    ('subject', 'lastname'),
    ('subject', 'firstname_hash'),  # unrecoverable, if anonymizing
    ('subject', 'lastname_hash'),   # unrecoverable, if anonymizing
    ('subject', 'sex'),
    ('subject', 'age'),
    ('acquisition', 'instrument'),
    ('acquisition', 'measurement'),
    ('file', 'instrument'),
    ('file', 'measurements'),
]


# monkey patching httplib to increase performance due to hard-coded block size
import httplib
from array import array

def fast_http_send(self, data):
    """Send `data' to the server."""
    if self.sock is None:
        if self.auto_open:
            self.connect()
        else:
            raise NotConnected()

    if self.debuglevel > 0:
        print "send:", repr(data)
    blocksize = 2**20 # was 8192 originally
    if hasattr(data,'read') and not isinstance(data, array):
        if self.debuglevel > 0: print "sendIng a read()able"
        datablock = data.read(blocksize)
        while datablock:
            self.sock.sendall(datablock)
            datablock = data.read(blocksize)
    else:
        self.sock.sendall(data)

httplib.HTTPConnection.send = fast_http_send
httplib.HTTPSConnection.send = fast_http_send


class ReaperItem(dict):

    def __init__(self, state, **kwargs):
        self['reaped'] = False
        self['failures'] = 0
        self['lastseen'] = datetime.datetime.utcnow()
        self['state'] = state
        self.update(kwargs)


class Reaper(object):

    peripheral_data_reapers = {}
    destructive = False

    def __init__(self, id_, options):
        self.id_ = id_
        self.persistence_file = options.get('persistence_file')
        self.upload_uris = options.get('upload') or []
        self.peripheral_data = dict(options.get('peripheral') or [])
        self.sleeptime = options.get('sleeptime') or SLEEPTIME
        self.graceperiod = datetime.timedelta(seconds=(options.get('graceperiod') or GRACEPERIOD))
        self.reap_existing = options.get('existing') or False
        self.insecure = options.get('insecure') or False
        self.tempdir = options.get('tempdir')
        self.timezone = options.get('timezone')
        self.oneshot = options.get('oneshot') or False
        self.working_hours = options.get('workinghours')

        self.state = {}
        self.alive = True

        if not self.upload_uris:
            log.warning('no upload URI provided; === DATA WILL BE PURGED AFTER REAPING ===')
        for uri in self.upload_uris:
            try:
                self.upload_method(uri)
            except ValueError as e:
                log.error(str(e))
                sys.exit(1)

        if self.timezone is None:
            self.timezone = tzlocal.get_localzone()
        else:
            try:
                self.timezone = pytz.timezone(self.timezone)
            except pytz.UnknownTimeZoneError:
                log.error('invalid timezone')
                sys.exit(1)

    def halt(self):
        self.alive = False

    def state_str(self, _id, state):
        pass

    def instrument_query(self):
        pass

    def reap(self, _id, item, tempdir):
        pass

    def destroy(self, item):
        pass

    def run(self):
        log.info('initializing ' + self.__class__.__name__ + '...')
        if self.oneshot or self.reap_existing:
            self.state = {}
        else:
            self.state = self.persistent_state
            if self.state:
                unreaped_cnt = len([v for v in self.state.itervalues() if not v['reaped']])
                log.info('loaded       %d items from persistence file, %d not reaped' % (len(self.state), unreaped_cnt))
            else:
                query_start = datetime.datetime.utcnow()
                self.state = self.instrument_query()
                if self.state is not None:
                    log.debug('query time   %.1fs' % (datetime.datetime.utcnow() - query_start).total_seconds())
                    for item in self.state.itervalues():
                        item['reaped'] = True
                    self.persistent_state = self.state
                    log.info('ignoring     %d items currently on instrument' % len(self.state))
                else:
                    log.warning('unable to retrieve instrument state')
                log.info('sleeping     %.1fs' % self.sleeptime)
                time.sleep(self.sleeptime)
        while self.alive:
            if not self.in_working_hours:
                log.info('sleeping     %.0fs (off-duty)' % OFFDUTY_SLEEPTIME)
                time.sleep(OFFDUTY_SLEEPTIME)
                continue
            query_start = datetime.datetime.utcnow()
            new_state = self.instrument_query()
            reap_start = datetime.datetime.utcnow()
            log.debug('query time   %.1fs' % (reap_start - query_start).total_seconds())
            if new_state is not None:
                reap_queue = []
                for _id, item in new_state.iteritems():
                    state_item = self.state.pop(_id, None)
                    if state_item:
                        item['reaped'] = state_item['reaped']
                        item['failures'] = state_item['failures']
                        if not item['reaped'] and item['state'] == state_item['state']:
                            reap_queue.append((_id, item))
                        elif item['state'] != state_item['state']:
                            item['reaped'] = False
                            log.info('monitoring   ' + self.state_str(_id, item['state']))
                    else:
                        log.info('discovered   ' + self.state_str(_id, item['state']))
                for _id, item in self.state.iteritems(): # retain absent, but recently seen, items
                    if item['lastseen'] + self.graceperiod > reap_start:
                        if not item.get('retained', False):
                            item['retained'] = True
                            log.debug('retaining    %s' % _id)
                        new_state[_id] = item
                    else:
                        log.debug('purging      %s' % _id)
                self.persistent_state = self.state = new_state
                reap_queue_len = len(reap_queue)
                for i, _id_item in enumerate(reap_queue):
                    if not self.in_working_hours:
                        log.info('aborting     reap-run (off-duty)')
                        break
                    _id, item = _id_item
                    log.info('reap queue   item %d of %d' % (i+1, reap_queue_len))
                    with tempfile.TemporaryDirectory(dir=self.tempdir) as tempdir:
                        item['reaped'], metadata_map = self.reap(_id, item, tempdir) # returns True, False, None
                        if item['reaped']:
                            item['failures'] = 0
                            if self.upload(metadata_map, tempdir):
                                if self.destructive:
                                    self.destroy(item)
                            else:
                                item['reaped'] = False
                        elif item['reaped'] is None: # mark skipped or discarded items as reaped
                            item['reaped'] = True
                        else:
                            item['failures'] += 1
                            log.warning('failure      %s (%d failures)' % (_id, item['failures']))
                            if item['failures'] > 9:
                                item['reaped'] = True
                                item['abandoned'] = True
                                log.warning('abandoning   ' + self.state_str(_id, item['state']))
                    self.persistent_state = self.state
                unreaped_cnt = len([v for v in self.state.itervalues() if not v['reaped']])
                log.info('monitoring   %d items, %d not reaped' % (len(self.state), unreaped_cnt))
                if self.oneshot and unreaped_cnt == 0:
                    break
            else:
                log.warning('unable to retrieve instrument state')
            sleeptime = self.sleeptime - (datetime.datetime.utcnow() - reap_start).total_seconds()
            if sleeptime > 0:
                log.debug('sleeping     %.1fs' % sleeptime)
                time.sleep(sleeptime)

    def metadata(self, obj):
        metadata = {
            'session': {'timezone': self.timezone},
            'acquisition': {'timezone': self.timezone},
        }
        for md_group, md_field in METADATA:
            value = getattr(obj, md_group + '_' + md_field, None)
            if value is not None:
                metadata.setdefault(md_group, {})
                metadata[md_group][md_field] = value
        metadata['session']['subject'] = metadata.pop('subject', {})    # FIXME HACK
        metadata['acquisition']['files'] = [metadata.pop('file', {})]   # FIXME HACK
        return metadata

    def is_desired_item(self, opt):
        if self.opt is None:
            return True
        if self.opt == 'in' and opt is not None and not re.match(self.opt_value, opt.lower()):
            return False
        if self.opt == 'out' and re.match(self.opt_value, opt.lower()):
            return False
        return True

    @property
    def in_working_hours(self):
        if not self.working_hours:
            return True
        local_now = datetime.datetime.now().time()
        off_duty = False
        if self.working_hours[0] < self.working_hours[1] and not self.working_hours[0] < local_now < self.working_hours[1]:
            return False
        if self.working_hours[0] > self.working_hours[1] and self.working_hours[1] < local_now < self.working_hours[0]:
            return False
        return True

    @property
    def persistent_state(self):
        try:
            with open(self.persistence_file, 'r') as persistence_file:
                state = json.load(persistence_file, object_hook=util.datetime_decoder)
            # TODO: add some consistency checks here and possibly drop state
        except:
            log.warning('persistence file not found')
            state = {}
        return state

    @persistent_state.setter
    def persistent_state(self, state):
        log.debug('updating persistence file')
        temp_persistence_file = '/.'.join(os.path.split(self.persistence_file))
        with open(temp_persistence_file, 'w') as persistence_file:
            json.dump(state, persistence_file, indent=4, separators=(',', ': '), default=util.datetime_encoder)
            persistence_file.write('\n')
        os.rename(temp_persistence_file, self.persistence_file)

    def reap_peripheral_data(self, reap_path, reap_data, reap_name, log_info):
        for pdn, pdp in self.peripheral_data.iteritems():
            if pdn in self.peripheral_data_reapers:
                # FIXME
                # import self.peripheral_data_reapers[pdn]
                # run self.peripheral_data_reapers[pdn].reap(...)
                self.peripheral_data_reapers[pdn](pdn, pdp, reap_path, reap_data, reap_name+'_'+pdn, log, log_info, self.tempdir)
            else:
                log.warning('periph data %s %s does not exist' % (log_info, pdn))

    def upload(self, metadata_map, path):
        for filename, metadata in metadata_map.iteritems():
            filepath = os.path.join(path, filename)
            log.info('hashing      %s' % filename)
            for uri in self.upload_uris:
                log.info('uploading    %s [%s] to %s' % (filename, util.hrsize(os.path.getsize(filepath)), uri))
                start = datetime.datetime.utcnow()
                success = self.upload_method(uri)(filename, filepath, metadata, uri)
                upload_duration = (datetime.datetime.utcnow() - start).total_seconds()
                if not success:
                    return False
                log.info('uploaded     %s [%s/s]' % (filename, util.hrsize(os.path.getsize(filepath)/upload_duration)))
        return True

    def upload_method(self, uri):
        """Helper to get an appropriate upload function based on protocol"""
        if uri.startswith('http://') or uri.startswith('https://'):
            return self.http_upload
        elif uri.startswith('s3://'):
            return self.s3_upload
        elif uri.startswith('file://'):
            return self.file_copy
        else:
            raise ValueError('bad upload URI "%s"' % uri)

    def http_upload(self, filename, filepath, metadata, uri):
        # TODO dedup this with util.upload_file()
        headers = {
            'User-Agent': 'SciTran Drone Reaper %s ' % self.id_,
        }
        uri, _, secret = uri.partition('?secret=')
        if secret:
            headers['X-SciTran-Auth'] = secret
        with open(filepath, 'rb') as fd:
            try:
                metadata['acquisition']['files'][0]['name'] = filename # FIXME HACK
                metadata_json = json.dumps(metadata, default=util.metadata_encoder)
                mpe = requests_toolbelt.multipart.encoder.MultipartEncoder(fields={'metadata': metadata_json, 'file': (filename, fd)})
                headers['Content-Type'] = mpe.content_type
                r = requests.post(uri, data=mpe, headers=headers, verify=not self.insecure)
            except requests.exceptions.ConnectionError as e:
                log.error('error        %s: %s' % (filename, e))
                return False
            else:
                if r.ok:
                    return True
                else:
                    log.warning('failure      %s: %s %s' % (filename, r.status_code, r.reason))
                    return False

    def s3_upload(self, filename, filepath, metadata, digest, uri):
        pass

    def file_copy(self, filename, filepath, metadata, digest, uri):
        pass


def main(cls, arg_parser_update=None):
    import signal
    import argparse

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('persistence_file', help='path to persistence file')
    arg_parser.add_argument('-p', '--peripheral', nargs=2, action='append', help='path to peripheral data')
    arg_parser.add_argument('-s', '--sleeptime', type=int, help='time to sleep before checking for new data [60s]')
    arg_parser.add_argument('-g', '--graceperiod', type=int, help='time to keep vanished data alive [24h]')
    arg_parser.add_argument('-t', '--tempdir', help='directory to use for temporary files')
    arg_parser.add_argument('-u', '--upload', action='append', help='upload URI')
    arg_parser.add_argument('-z', '--timezone', help='instrument timezone [system timezone]')
    arg_parser.add_argument('-x', '--existing', action='store_true', help='retrieve all existing data')
    arg_parser.add_argument('-o', '--oneshot', action='store_true', help='retrieve all existing data and exit')
    arg_parser.add_argument('-l', '--loglevel', default='info', help='log level [INFO]')
    arg_parser.add_argument('-i', '--insecure', action='store_true', help='do not verify server SSL certificates')
    arg_parser.add_argument('-k', '--workinghours', nargs=2, type=int, help='working hours in 24hr time [0 24]')

    if arg_parser_update is not None:
        arg_parser = arg_parser_update(arg_parser)
    args = arg_parser.parse_args()

    log.setLevel(getattr(logging, args.loglevel.upper()))

    persistence_dir = os.path.normpath(os.path.dirname(args.persistence_file))
    if not os.path.isdir(persistence_dir):
        os.makedirs(persistence_dir)

    if args.insecure:
        requests.packages.urllib3.disable_warnings()

    if args.workinghours:
        args.workinghours = map(datetime.time, args.workinghours)

    log.debug(args)

    reaper = cls(vars(args))

    def term_handler(signum, stack):
        reaper.halt()
        log.warning('received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    reaper.run()
    log.warning('process halted')
