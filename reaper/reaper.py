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

log = logging.getLogger('reaper')

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

    def __init__(self, id_, options):
        self.id_ = id_
        self.state = {}
        self.alive = True
        self.opt = None
        self.opt_value = None
        self.upload_targets = []
        self.unreaped_cnt = 0

        self.persistence_file = options.get('persistence_file')
        self.sleeptime = options.get('sleeptime') or SLEEPTIME
        self.graceperiod = datetime.timedelta(seconds=(options.get('graceperiod') or GRACEPERIOD))
        self.ignore_existing = options.get('ignore_existing') or False
        self.tempdir = options.get('tempdir')
        self.timezone = options.get('timezone')
        self.working_hours = options.get('workinghours')
        self.oneshot = options.get('oneshot')

        if options['opt_in']:
            self.opt = 'in'
        elif options['opt_out']:
            self.opt = 'out'
        else:
            self.opt = None
            self.opt_key = self.opt_value = None
        if self.opt is not None:
            self.opt_key = options['opt_' + self.opt][0]
            self.opt_value = options['opt_' + self.opt][1].lower()
            if options.get('exact_opt_match'):
                self.opt_value = '^' + self.opt_value + '$'
            else:
                self.opt_value = '.*' + self.opt_value + '.*'
        self.map_key = options['map_key']

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

    def before_run(self):
        """
        Operations for before the run loop.
        """
        pass

    def before_reap(self, _id):
        """
        Operations for before the series is reaped.
        """
        pass

    def after_reap_success(self, _id):
        """
        Operations after the series is reaped successfully.

        Executed before after_reap()
        """
        pass

    def after_reap(self, _id):
        """
        Operations after the series is reaped, regardless of result.
        """
        pass

    def __get_instrument_state(self):
        query_start = datetime.datetime.utcnow()
        state = self.instrument_query()
        if state is None:
            log.warning('unable to retrieve instrument state')
        else:
            log.info('query time   %.1fs', (datetime.datetime.utcnow() - query_start).total_seconds())
        return state

    def __set_initial_state(self):
        # pylint: disable=missing-docstring
        log.info('initializing ' + self.__class__.__name__ + '...')
        self.state = self.persistent_state
        if not self.state:
            self.state = self.__get_instrument_state()
            if self.state is None:
                log.critical('cannot continue without instrument state')
                sys.exit(1)
            else:
                self.persistent_state = self.state
                if self.ignore_existing:
                    log.info('ignoring     %d items currently on instrument', len(self.state))
                    for item in self.state.itervalues():
                        item['reaped'] = True
                else:
                    log.info('discovered   %d items on instrument', len(self.state))
            log.info('sleeping     %.1fs', self.sleeptime)
            time.sleep(self.sleeptime)
        else:
            unreaped_cnt = len([v for v in self.state.itervalues() if not v['reaped']])
            log.info('loaded %d items from persistence file, %d not reaped', len(self.state), unreaped_cnt)
            log.info('*** delete persistence file to reset ***')

    def __build_reap_queue(self, new_state):
        reap_queue = []
        for _id, new_item in new_state.iteritems():
            item = self.state.get(_id)
            if item:
                new_item['reaped'] = item['reaped']
                new_item['failures'] = item['failures']
                if not item['reaped'] and new_item['state'] == item['state']:
                    reap_queue.append((_id, new_item))  # TODO avoid weird tuples, maybe include id in item
                elif new_item['state'] != item['state']:
                    new_item['reaped'] = False
                    log.info('monitoring   ' + self.state_str(_id, new_item['state']))
            else:
                log.info('discovered   ' + self.state_str(_id, new_item['state']))
        return reap_queue

    def __prune_stale_state(self, reap_start):
        for _id in [_id for _id, item in self.state.iteritems() if item['lastseen'] + self.graceperiod < reap_start]:
            log.info('purging      %s', _id)
            self.state.pop(_id)

    def __process_reap_queue(self, reap_queue):
        reap_queue_len = len(reap_queue)
        for i, _id_item in enumerate(reap_queue):
            if not self.in_working_hours:
                log.info('aborting     reap-run (off-duty)')
                break
            _id, item = _id_item
            log.info('reap queue   item %d of %d', i + 1, reap_queue_len)
            with tempfile.TemporaryDirectory(dir=self.tempdir) as tempdir:
                self.before_reap(_id)
                item['reaped'], metadata_map = self.reap(_id, item, tempdir)  # returns True, False, None
                if item['reaped']:
                    item['failures'] = 0
                    item['reaped'] = upload.upload_many(metadata_map, self.upload_targets)
                elif item['reaped'] is None:  # mark skipped or discarded items as reaped
                    item['reaped'] = True
                else:
                    item['failures'] += 1
                    log.warning('failure      %s (%d failures)', _id, item['failures'])
                    if item['failures'] > 9:
                        item['reaped'] = True
                        item['abandoned'] = True
                        log.warning('abandoning   ' + self.state_str(_id, item['state']))
                if item['reaped']:
                    self.after_reap_success(_id)
                self.after_reap(_id)
            self.persistent_state = self.state

    def run(self):
        # pylint: disable=missing-docstring
        self.before_run()
        self.__set_initial_state()
        while self.alive:
            if not self.in_working_hours:
                log.info('sleeping     %.0fs (off-duty)', OFFDUTY_SLEEPTIME)
                time.sleep(OFFDUTY_SLEEPTIME)
                continue
            new_state = self.__get_instrument_state()
            reap_start = datetime.datetime.utcnow()
            if new_state is not None:
                reap_queue = self.__build_reap_queue(new_state)
                self.state.update(new_state)
                self.__prune_stale_state(reap_start)
                self.persistent_state = self.state
                self.__process_reap_queue(reap_queue)
                self.unreaped_cnt = len([v for v in self.state.itervalues() if not v['reaped']])
                log.info('monitoring   %d items, %d not reaped', len(self.state), self.unreaped_cnt)
            if self.oneshot:
                break
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


def main(cls, arg_parser_update=None):
    # pylint: disable=missing-docstring
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('persistence_file', help='path to persistence file')
    arg_parser.add_argument('-s', '--sleeptime', type=int, help='time to sleep before checking for new data [60s]')
    arg_parser.add_argument('-g', '--graceperiod', type=int, help='time to keep vanished data alive [24h]')
    arg_parser.add_argument('-t', '--tempdir', help='directory to use for temporary files')
    arg_parser.add_argument('-u', '--upload', action='append', default=[], help='upload URI')
    arg_parser.add_argument('-z', '--timezone', help='instrument timezone [system timezone]')
    arg_parser.add_argument('-x', '--ignore_existing', action='store_true', help='ignore existing data')
    arg_parser.add_argument('-l', '--loglevel', default='info', help='log level [INFO]')
    arg_parser.add_argument('-i', '--insecure', action='store_true', help='do not verify server SSL certificates')
    arg_parser.add_argument('-k', '--workinghours', nargs=2, type=int, help='working hours in 24hr time [0 24]')
    arg_parser.add_argument('-o', '--oneshot', action='store_true', help='break out of runloop after one iteration (for testing)')

    arg_parser.add_argument('--map-key', default='PatientID', help='key for mapping info [PatientID], patterned as subject@group/project')
    opt_group = arg_parser.add_mutually_exclusive_group()
    opt_group.add_argument('--opt-in', nargs=2, help='opt-in key and value (case-insensitive substring matching)')
    opt_group.add_argument('--opt-out', nargs=2, help='opt-out key and value (case-insensitive substring matching)')
    arg_parser.add_argument('--exact-opt-match', action='store_true', help='use case-insensitive full-string opt matching')

    if arg_parser_update is not None:
        arg_parser = arg_parser_update(arg_parser)
    args = arg_parser.parse_args()

    log.setLevel(getattr(logging, args.loglevel.upper()))

    args.persistence_file = os.path.abspath(args.persistence_file)
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

    sys.exit(reaper.unreaped_cnt > 0)
    log.warning('process halted')
