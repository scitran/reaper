# @author:  Gunnar Schaefer

import logging
logging.basicConfig(
        format='%(asctime)s %(name)16.16s:%(levelname)4.4s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=logging.DEBUG,
        )
log = logging.getLogger('reaper')
logging.getLogger('requests').setLevel(logging.WARNING)

import os
import json
import time
import hashlib
import tarfile
import calendar
import datetime
import requests

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


class ReaperOptions(object):

    def __init__(self, args):
        self.upload_urls = args.upload
        self.pat_id = args.patid.replace('*','.*')
        self.discard_ids = args.discard.split()
        self.peripheral_data = dict(args.peripheral)
        self.sleep_time = args.sleeptime
        self.tempdir = args.tempdir
        self.anonymize = args.anonymize
        self.existing = args.existing
        self.timezone = args.timezone


class Reaper(object):

    peripheral_data_reapers = {}

    def __init__(self, id_, options):
        self.id_ = id_
        self.options = options
        self.persitence_file = os.path.join(os.path.dirname(__file__), '.%s.json' % self.id_)
        self.state = self.persistent_state
        self.alive = True

    def state_str(self, state):
        return ', '.join(['%s: %s' %i for i in state.iteritems()])

    def halt(self):
        self.alive = False

    def run(self):
        while self.alive:
            iteration_start = datetime.datetime.now()
            new_state = self.instrument_query()
            if new_state:
                for _id, item in new_state.iteritems():
                    if _id in self.state:
                        item['failures'] = self.state[_id]['failures']
                        if not self.state[_id]['reaped'] and item['state'] == self.state[_id]['state']:
                            item['reaped'] = self.reap(item)
                        elif item['state'] != self.state[_id]['state']:
                            item['reaped'] = False
                            log.info('monitoring   %s (%s)' % (item['_id'], self.state_str(item['state'])))
                        else:
                            item['reaped'] = True
                    else:
                        item['reaped'] = False
                        item['failures'] = 0
                        log.info('discovered   %s (%s)' % (item['_id'], self.state_str(item['state'])))
                self.persistent_state = self.state = new_state
                iteration_runtime = (datetime.datetime.now() - iteration_start).total_seconds()
                log.info('monitoring   %d items, %d not reaped' % (len(self.state), len([v for v in self.state.itervalues() if not v['reaped']])))
            else:
                log.warning('unable to retrieve instrument state')
            log.debug('reap time    %.1fs' % iteration_runtime)
            sleep_time = self.options.sleep_time - iteration_runtime
            if sleep_time > 0:
                log.info('sleeping     %.1fs' % sleep_time)
                time.sleep(sleep_time)

    def get_persistent_state(self):
        log.info('initializing ' + self.__class__.__name__)
        if self.options.existing:
            state = {}
        else:
            try:
                with open(self.persitence_file, 'r') as persitence_file:
                    state = json.load(persitence_file, object_hook=datetime_decoder)
                log.info('loaded       %d items from persistence file' % len(state))
            except:
                state = self.instrument_query()
                for item in state.itervalues():
                    item['reaped'] = True
                    item['failures'] = 0
                self.set_persistent_state(state)
                log.info('ignoring     %d items currently on instrument' % len(state))
                time.sleep(self.options.sleep_time)
        return state
    def set_persistent_state(self, state):
        with open(self.persitence_file, 'w') as persitence_file:
            json.dump(state, persitence_file, indent=4, separators=(',', ': '), default=datetime_encoder)
            persitence_file.write('\n')
    persistent_state = property(get_persistent_state, set_persistent_state)

    def reap_peripheral_data(self, reap_path, reap_data, reap_name, log_info):
        for pdn, pdp in self.options.peripheral_data.iteritems():
            if pdn in self.peripheral_data_reapers:
                self.peripheral_data_reapers[pdn](pdn, pdp, reap_path, reap_data, reap_name+'_'+pdn, log, log_info, self.options.tempdir)
            else:
                log.warning('periph data %s %s does not exist' % (log_info, pdn))

    def upload(self, path, log_info):
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            log.info('hashing      %s' % filename)
            hash_ = hashlib.sha1()
            with open(filepath, 'rb') as fd:
                for chunk in iter(lambda: fd.read(1048577 * hash_.block_size), ''):
                    hash_.update(chunk)
            headers = {'User-Agent': 'reaper ' + self.id_, 'Content-MD5': hash_.hexdigest()}
            for url in self.options.upload_urls:
                log.info('uploading    %s [%s] to %s' % (filename, hrsize(os.path.getsize(filepath)), url))
                with open(filepath, 'rb') as fd:
                    try:
                        start = datetime.datetime.now()
                        r = requests.put(url + '?filename=%s_%s' % (self.id_, filename), data=fd, headers=headers)
                        upload_duration = (datetime.datetime.now() - start).total_seconds()
                    except requests.exceptions.ConnectionError as e:
                        log.error('error        %s: %s' % (filename, e))
                        return False
                    else:
                        if r.status_code in [200, 202]:
                            log.debug('success      %s [%s/s]' % (filename, hrsize(os.path.getsize(filepath)/upload_duration)))
                        else:
                            log.warning('failure      %s: %s %s' % (filename, r.status_code, r.reason))
                            return False
        return True


def main(cls):
    import sys
    import pytz
    import signal
    import tzlocal
    import argparse

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('class_args', help='subclass arguments')
    arg_parser.add_argument('-A', '--no-anonymize', dest='anonymize', action='store_false', help='do not anonymize patient name and birthdate')
    arg_parser.add_argument('-d', '--discard', default='discard', help='space-separated list of Patient IDs to discard')
    arg_parser.add_argument('-i', '--patid', default='*', help='glob for Patient IDs to reap (default: "*")')
    arg_parser.add_argument('-p', '--peripheral', nargs=2, action='append', default=[], help='path to peripheral data')
    arg_parser.add_argument('-s', '--sleeptime', type=int, default=60, help='time to sleep before checking for new data')
    arg_parser.add_argument('-t', '--tempdir', help='directory to use for temporary files')
    arg_parser.add_argument('-u', '--upload', action='append', help='upload URL')
    arg_parser.add_argument('-x', '--existing', action='store_true', help='retrieve all existing data')
    arg_parser.add_argument('-z', '--timezone', help='instrument timezone [system timezone]')
    args = arg_parser.parse_args()

    if args.timezone is None:
        args.timezone = tzlocal.get_localzone().zone
    else:
        try:
            pytz.timezone(args.timezone)
        except pytz.UnknownTimeZoneError:
            log.error('invalid timezone')
            sys.exit(1)

    options = ReaperOptions(args)
    reaper = cls(args.class_args, options)

    def term_handler(signum, stack):
        reaper.halt()
        log.warning('received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    reaper.run()
    log.warning('process halted')
