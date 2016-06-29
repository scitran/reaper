"""SciTran Reaper base class"""

import os
import re
import sys
import time
import signal
import logging
import argparse
import datetime


from . import util
from . import upload
from . import tempdir as tempfile

log = logging.getLogger(__name__)

SLEEPTIME = 60
GRACEPERIOD = 86400
OFFDUTY_SLEEPTIME = 300
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class ReaperItem(dict):

    """ReaperItem class"""

    def __init__(self, state, **kwargs):
        super(ReaperItem, self).__init__()
        self['reaped'] = False
        self['failures'] = 0
        self['lastseen'] = datetime.datetime.utcnow()
        self['state'] = state
        self.update(kwargs)


class Reaper(object):

    """Reaper class"""

    peripheral_data_reapers = {}
    destructive = False

    def __init__(self, id_, options):
        self.id_ = id_
        self.state = {}
        self.alive = True
        self.opt = None
        self.opt_value = None
        self.upload_targets = []

        self.persistence_file = options.get('persistence_file')
        self.peripheral_data = dict(options.get('peripheral') or [])
        self.sleeptime = options.get('sleeptime') or SLEEPTIME
        self.graceperiod = datetime.timedelta(seconds=(options.get('graceperiod') or GRACEPERIOD))
        self.reap_existing = options.get('existing') or False
        self.tempdir = options.get('tempdir')
        self.timezone = options.get('timezone')
        self.oneshot = options.get('oneshot') or False
        self.working_hours = options.get('workinghours')

        if options['opt_in']:
            self.opt = 'in'
        elif options['opt_out']:
            self.opt = 'out'
        else:
            self.opt = None
            self.opt_field = self.opt_value = None
        if self.opt is not None:
            self.opt_field = options['opt_' + self.opt][0]
            self.opt_value = '.*' + options['opt_' + self.opt][1].lower() + '.*'
        self.id_field = options['id_field']

    def halt(self):
        # pylint: disable=missing-docstring
        self.alive = False

    def state_str(self, _id, state):
        # pylint: disable=missing-docstring
        pass

    def instrument_query(self):
        # pylint: disable=missing-docstring
        pass

    def reap(self, _id, item, tempdir):
        # pylint: disable=missing-docstring
        pass

    def destroy(self, item):
        # pylint: disable=missing-docstring
        pass

    def run(self):
        # pylint: disable=missing-docstring,too-many-branches,too-many-statements
        log.info('initializing ' + self.__class__.__name__ + '...')
        if self.oneshot or self.reap_existing:
            self.state = {}
        else:
            self.state = self.persistent_state
            if self.state:
                unreaped_cnt = len([v for v in self.state.itervalues() if not v['reaped']])
                log.info('loaded       %d items from persistence file, %d not reaped', len(self.state), unreaped_cnt)
            else:
                query_start = datetime.datetime.utcnow()
                self.state = self.instrument_query()
                if self.state is not None:
                    log.info('query time   %.1fs', (datetime.datetime.utcnow() - query_start).total_seconds())
                    for item in self.state.itervalues():
                        item['reaped'] = True
                    self.persistent_state = self.state
                    log.info('ignoring     %d items currently on instrument', len(self.state))
                else:
                    log.warning('unable to retrieve instrument state')
                log.info('sleeping     %.1fs', self.sleeptime)
                time.sleep(self.sleeptime)
        while self.alive:
            if not self.in_working_hours:
                log.info('sleeping     %.0fs (off-duty)', OFFDUTY_SLEEPTIME)
                time.sleep(OFFDUTY_SLEEPTIME)
                continue
            query_start = datetime.datetime.utcnow()
            new_state = self.instrument_query()
            reap_start = datetime.datetime.utcnow()
            log.debug('query time   %.1fs', (reap_start - query_start).total_seconds())
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
                for _id, item in self.state.iteritems():  # retain absent, but recently seen, items
                    if item['lastseen'] + self.graceperiod > reap_start:
                        if not item.get('retained', False):
                            item['retained'] = True
                            log.info('retaining    %s', _id)
                        new_state[_id] = item
                    else:
                        log.info('purging      %s', _id)
                self.persistent_state = self.state = new_state
                reap_queue_len = len(reap_queue)
                for i, _id_item in enumerate(reap_queue):
                    if not self.in_working_hours:
                        log.info('aborting     reap-run (off-duty)')
                        break
                    _id, item = _id_item
                    log.info('reap queue   item %d of %d', i + 1, reap_queue_len)
                    with tempfile.TemporaryDirectory(dir=self.tempdir) as tempdir:
                        item['reaped'], metadata_map = self.reap(_id, item, tempdir)  # returns True, False, None
                        if item['reaped']:
                            item['failures'] = 0
                            if upload.upload_many(metadata_map, self.upload_targets):
                                if self.destructive:
                                    self.destroy(item)
                            else:
                                item['reaped'] = False
                        elif item['reaped'] is None:  # mark skipped or discarded items as reaped
                            item['reaped'] = True
                        else:
                            item['failures'] += 1
                            log.warning('failure      %s (%d failures)', _id, item['failures'])
                            if item['failures'] > 9:
                                item['reaped'] = True
                                item['abandoned'] = True
                                log.warning('abandoning   ' + self.state_str(_id, item['state']))
                    self.persistent_state = self.state
                unreaped_cnt = len([v for v in self.state.itervalues() if not v['reaped']])
                log.info('monitoring   %d items, %d not reaped', len(self.state), unreaped_cnt)
                if self.oneshot and unreaped_cnt == 0:
                    break
            else:
                log.warning('unable to retrieve instrument state')
            sleeptime = self.sleeptime - (datetime.datetime.utcnow() - reap_start).total_seconds()
            if sleeptime > 0:
                log.info('sleeping     %.1fs', sleeptime)
                time.sleep(sleeptime)

    def is_desired_item(self, opt):
        # pylint: disable=missing-docstring
        if self.opt is None:
            return True
        if self.opt == 'in' and opt is not None and not re.match(self.opt_value, opt.lower()):
            return False
        if self.opt == 'out' and re.match(self.opt_value, opt.lower()):
            return False
        return True

    @property
    def in_working_hours(self):
        # pylint: disable=missing-docstring
        if not self.working_hours:
            return True
        local_now = datetime.datetime.now().time()
        if self.working_hours[0] < self.working_hours[1] and not self.working_hours[0] < local_now < self.working_hours[1]:
            return False
        if self.working_hours[0] > self.working_hours[1] and self.working_hours[1] < local_now < self.working_hours[0]:
            return False
        return True

    @property
    def persistent_state(self):
        # pylint: disable=missing-docstring
        return util.read_state_file(self.persistence_file)

    @persistent_state.setter
    def persistent_state(self, state):
        # pylint: disable=missing-docstring
        log.debug('persisting   instrument state')
        util.write_state_file(self.persistence_file, state)

    def reap_peripheral_data(self, reap_path, reap_data, reap_name, log_info):
        # pylint: disable=missing-docstring
        for pdn, pdp in self.peripheral_data.iteritems():
            if pdn in self.peripheral_data_reapers:
                # FIXME
                # import self.peripheral_data_reapers[pdn]
                # run self.peripheral_data_reapers[pdn].reap(...)
                self.peripheral_data_reapers[pdn](pdn, pdp, reap_path, reap_data, reap_name + '_' + pdn, log, log_info, self.tempdir)
            else:
                log.warning('periph data %s %s does not exist', log_info, pdn)


def main(cls, arg_parser_update=None):
    # pylint: disable=missing-docstring
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('persistence_file', help='path to persistence file')
    arg_parser.add_argument('-p', '--peripheral', nargs=2, action='append', help='path to peripheral data')
    arg_parser.add_argument('-s', '--sleeptime', type=int, help='time to sleep before checking for new data [60s]')
    arg_parser.add_argument('-g', '--graceperiod', type=int, help='time to keep vanished data alive [24h]')
    arg_parser.add_argument('-t', '--tempdir', help='directory to use for temporary files')
    arg_parser.add_argument('-u', '--upload', action='append', default=[], help='upload URI')
    arg_parser.add_argument('-z', '--timezone', help='instrument timezone [system timezone]')
    arg_parser.add_argument('-x', '--existing', action='store_true', help='retrieve all existing data')
    arg_parser.add_argument('-o', '--oneshot', action='store_true', help='retrieve all existing data and exit')
    arg_parser.add_argument('-l', '--loglevel', default='info', help='log level [INFO]')
    arg_parser.add_argument('-i', '--insecure', action='store_true', help='do not verify server SSL certificates')
    arg_parser.add_argument('-k', '--workinghours', nargs=2, type=int, help='working hours in 24hr time [0 24]')

    arg_parser.add_argument('--id-field', default='PatientID', help='DICOM field for id info [PatientID]')
    opt_group = arg_parser.add_mutually_exclusive_group()
    opt_group.add_argument('--opt-in', nargs=2, help='opt-in field and value')
    opt_group.add_argument('--opt-out', nargs=2, help='opt-out field and value')

    if arg_parser_update is not None:
        arg_parser = arg_parser_update(arg_parser)
    args = arg_parser.parse_args()

    log.setLevel(getattr(logging, args.loglevel.upper()))

    persistence_dir = os.path.normpath(os.path.dirname(args.persistence_file))
    if not os.path.isdir(persistence_dir):
        os.makedirs(persistence_dir)

    if args.workinghours:
        args.workinghours = [datetime.time(i) for i in args.workinghours]

    args.timezone = util.validate_timezone(args.timezone)
    if args.timezone is None:
        log.error('invalid timezone')
        sys.exit(1)

    log.debug(args)

    reaper = cls(vars(args))
    if not args.upload:
        log.warning('no upload URI provided; === DATA WILL BE PURGED AFTER REAPING ===')
    for uri in args.upload:
        try:
            reaper.upload_targets.append(
                upload.upload_function(uri, ('reaper', reaper.id_), insecure=args.insecure, upload_route='/upload/uid')[1]
            )
        except ValueError as ex:
            log.error(str(ex))
            sys.exit(1)

    def term_handler(signum, stack):
        # pylint: disable=missing-docstring,unused-argument
        reaper.halt()
        log.warning('received SIGTERM - shutting down...')
    signal.signal(signal.SIGTERM, term_handler)

    reaper.run()
    log.warning('process halted')
