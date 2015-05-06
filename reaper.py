# @author:  Gunnar Schaefer

import logging
logging.basicConfig(
        format='%(asctime)s %(name)16.16s:%(levelname)4.4s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        )
log = logging.getLogger('reaper')
logging.getLogger('requests').setLevel(logging.WARNING)

import os
import sys
import json
import pytz
import time
import hashlib
import tarfile
import tzlocal
import calendar
import datetime
import requests

import tempdir as tempfile

SLEEPTIME = 60
GRACEPERIOD = 86400
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def hrsize(size):
    if size < 1000:
        return '%d%s' % (size, 'B')
    for suffix in 'KMGTPEZY':
        size /= 1024.
        if size < 10.:
            return '%.1f%s' % (size, suffix)
        if size < 1000.:
            return '%.0f%s' % (size, suffix)
    return '%.0f%s' % (size, 'Y')


def datetime_encoder(o):
    if isinstance(o, datetime.datetime):
        if o.utcoffset() is not None:
            o = o - o.utcoffset()
        return {"$date": int(calendar.timegm(o.timetuple()) * 1000 + o.microsecond / 1000)}
    raise TypeError(repr(o) + " is not JSON serializable")


def datetime_decoder(dct):
    if "$date" in dct:
        return datetime.datetime.utcfromtimestamp(float(dct["$date"]) / 1000.0)
    return dct


def create_archive(path, content, arcname, metadata, **kwargs):
    # write metadata file
    metadata_filepath = os.path.join(content, 'METADATA.json')
    with open(metadata_filepath, 'w') as json_file:
        json.dump(metadata, json_file, default=datetime_encoder)
        json_file.write('\n')
    # write digest file
    digest_filepath = os.path.join(content, 'DIGEST.txt')
    open(digest_filepath, 'w').close() # touch file, so that it's included in the digest
    filenames = sorted(os.listdir(content), key=lambda fn: (fn.endswith('.json') and 1) or (fn.endswith('.txt') and 2) or fn)
    with open(digest_filepath, 'w') as digest_file:
        digest_file.write('\n'.join(filenames) + '\n')
    # create archive
    with tarfile.open(path, 'w:gz', **kwargs) as archive:
        archive.add(content, arcname, recursive=False) # add the top-level directory
        for fn in filenames:
            archive.add(os.path.join(content, fn), os.path.join(arcname, fn))


class ReaperItem(dict):

    def __init__(self, state, **kwargs):
        self['reaped'] = False
        self['failures'] = 0
        self['lastseen'] = datetime.datetime.utcnow()
        self['state'] = state
        self.update(kwargs)


class Reaper(object):

    peripheral_data_reapers = {}

    def __init__(self, id_, options):
        self.id_ = id_
        self.upload_uris = options.get('upload') or []
        self.peripheral_data = dict(options.get('peripheral') or [])
        self.sleeptime = options.get('sleeptime') or SLEEPTIME
        self.graceperiod = datetime.timedelta(seconds=(options.get('graceperiod') or GRACEPERIOD))
        self.reap_existing = options.get('existing') or False
        self.tempdir = options.get('tempdir')
        self.timezone = options.get('timezone')
        self.oneshot = options.get('oneshot') or False
        log.setLevel(getattr(logging, (options.get('loglevel') or 'info').upper()))

        self.state = {}
        self.persitence_file = os.path.join(os.path.dirname(__file__), '.%s.json' % self.id_)
        self.alive = True

        if not options.get('upload'):
            log.warning('no upload URI provided; === DATA WILL BE PURGED AFTER REAPING ===')

        if self.timezone is None:
            self.timezone = tzlocal.get_localzone().zone
        else:
            try:
                pytz.timezone(self.timezone)
            except pytz.UnknownTimeZoneError:
                log.error('invalid timezone')
                sys.exit(1)

    def halt(self):
        self.alive = False

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
                query_start = datetime.datetime.now()
                self.state = self.instrument_query()
                if self.state is not None:
                    log.debug('query time   %.1fs' % (datetime.datetime.now() - query_start).total_seconds())
                    for item in self.state.itervalues():
                        item['reaped'] = True
                    self.persistent_state = self.state
                    log.info('ignoring     %d items currently on instrument' % len(self.state))
                else:
                    log.warning('unable to retrieve instrument state')
                log.info('sleeping     %.1fs' % self.sleeptime)
                time.sleep(self.sleeptime)
        while self.alive:
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
                    _id, item = _id_item
                    log.info('reap queue   item %d of %d' % (i+1, reap_queue_len))
                    with tempfile.TemporaryDirectory(dir=self.tempdir) as tempdir:
                        item['reaped'] = self.reap(_id, item, tempdir) # returns True, False, None
                        if item['reaped']:
                            item['failures'] = 0
                            if not self.upload(tempdir):
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

    @property
    def persistent_state(self):
        try:
            with open(self.persitence_file, 'r') as persitence_file:
                state = json.load(persitence_file, object_hook=datetime_decoder)
            # TODO: add some consistency checks here and possibly drop state
        except:
            state = {}
        return state

    @persistent_state.setter
    def persistent_state(self, state):
        with open(self.persitence_file, 'w') as persitence_file:
            json.dump(state, persitence_file, indent=4, separators=(',', ': '), default=datetime_encoder)
            persitence_file.write('\n')

    def reap_peripheral_data(self, reap_path, reap_data, reap_name, log_info):
        for pdn, pdp in self.peripheral_data.iteritems():
            if pdn in self.peripheral_data_reapers:
                self.peripheral_data_reapers[pdn](pdn, pdp, reap_path, reap_data, reap_name+'_'+pdn, log, log_info, self.tempdir)
            else:
                log.warning('periph data %s %s does not exist' % (log_info, pdn))

    def upload(self, path):
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            log.info('hashing      %s' % filename)
            hash_ = hashlib.sha1()
            with open(filepath, 'rb') as fd:
                for chunk in iter(lambda: fd.read(1048577 * hash_.block_size), ''):
                    hash_.update(chunk)
            digest = hash_.hexdigest()
            for uri in self.upload_uris:
                log.info('uploading    %s [%s] to %s' % (filename, hrsize(os.path.getsize(filepath)), uri))
                start = datetime.datetime.utcnow()
                if uri.startswith('http://') or uri.startswith('https://'):
                    success = self.http_upload(filename, filepath, digest, uri)
                elif uri.startswith('s3://'):
                    success = self.s3_upload(filename, filepath, digest, uri)
                elif uri.startswith('file://'):
                    success = self.file_copy(filename, filepath, digest, uri)
                else:
                    log.error('unknown URI schem: %s' % uri)
                    return False
                upload_duration = (datetime.datetime.utcnow() - start).total_seconds()
                if success:
                    log.info('uploaded     %s [%s/s]' % (filename, hrsize(os.path.getsize(filepath)/upload_duration)))
                else:
                    return False
        return True

    def http_upload(self, filename, filepath, digest, uri):
        headers = {'User-Agent': 'reaper ' + self.id_, 'Content-MD5': digest}
        with open(filepath, 'rb') as fd:
            try:
                r = requests.put(uri + '?filename=%s_%s' % (self.id_, filename), data=fd, headers=headers)
            except requests.exceptions.ConnectionError as e:
                log.error('error        %s: %s' % (filename, e))
                return False
            else:
                if r.status_code in [200, 202]:
                    return True
                else:
                    log.warning('failure      %s: %s %s' % (filename, r.status_code, r.reason))
                    return False

    def s3_upload(self, filename, filepath, digest, uri):
        pass

    def file_copy(self, filename, filepath, digest, uri):
        pass


def main(cls, positional_args, optional_args):
    import signal
    import argparse

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('-p', '--peripheral', nargs=2, action='append', help='path to peripheral data')
    arg_parser.add_argument('-s', '--sleeptime', type=int, help='time to sleep before checking for new data [60s]')
    arg_parser.add_argument('-g', '--graceperiod', type=int, help='time to keep vanished data alive [24h]')
    arg_parser.add_argument('-t', '--tempdir', help='directory to use for temporary files')
    arg_parser.add_argument('-u', '--upload', action='append', help='upload URI')
    arg_parser.add_argument('-z', '--timezone', help='instrument timezone [system timezone]')
    arg_parser.add_argument('-x', '--existing', action='store_true', help='retrieve all existing data')
    arg_parser.add_argument('-o', '--oneshot', action='store_true', help='retrieve all existing data and exit')
    arg_parser.add_argument('-l', '--loglevel', help='log level [INFO]')

    pg = arg_parser.add_argument_group(cls.__name__ + ' arguments')
    for args, kwargs in positional_args:
        pg.add_argument(*args, **kwargs)
    og = arg_parser.add_argument_group(cls.__name__ + ' options')
    for args, kwargs in optional_args:
        og.add_argument(*args, **kwargs)
    args = arg_parser.parse_args()

    reaper = cls(vars(args))

    def term_handler(signum, stack):
        reaper.halt()
        log.warning('received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    reaper.run()
    log.warning('process halted')
