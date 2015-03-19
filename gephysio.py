# @author:  Gunnar Schaefer

import os
import re
import time
import shutil
import datetime

import reaper
import tempdir as tempfile

import scitran.data.medimg.gephysio


def reap(name, data_path, reap_path, reap_data, reap_name, log, log_info, tempdir):
    lower_time_bound = reap_data.timestamp + datetime.timedelta(seconds=reap_data.prescribed_duration or 0) - datetime.timedelta(seconds=15)
    upper_time_bound = lower_time_bound + datetime.timedelta(seconds=180)
    sleep_time = (upper_time_bound - datetime.datetime.now()).total_seconds()
    if sleep_time > 0:
        log.info('periph data  %s waiting for %s for %ds' % (log_info, name, sleep_time))
        time.sleep(sleep_time)
    for i in range(15):
        try:
            physio_files = os.listdir(data_path)
        except OSError:
            physio_files = []
        if physio_files:
            break
        else:
            log.warning('periph data  %s %s temporarily unavailable' % (log_info, name))
            time.sleep(60)
    else:
        log.error('periph data  %s %s permanently unavailable - giving up' % (log_info, name))
        return
    physio_tuples = filter(lambda pt: pt[0], [(re.match('.+_%s_([0-9_]{18,20})$' % reap_data.psd_name, pfn), pfn) for pfn in physio_files])
    physio_tuples = [(datetime.datetime.strptime(pts.group(1), '%m%d%Y%H_%M_%S_%f'), pfn) for pts, pfn in physio_tuples]
    physio_tuples = filter(lambda pt: lower_time_bound <= pt[0] <= upper_time_bound, physio_tuples)
    if physio_tuples:
        log.info('periph data  %s %s found' % (log_info, name))
        with tempfile.TemporaryDirectory(dir=tempdir) as tempdir_path:
            metadata = {
                    'filetype': scitran.data.medimg.gephysio.GEPhysio.filetype,
                    'timezone': reap_data.nims_timezone,
                    'header': {
                        'group': reap_data.nims_group_id,
                        'project': reap_data.nims_project,
                        'session': reap_data.nims_session_id,
                        'acquisition': reap_data.nims_acquisition_id,
                        'timestamp': reap_data.nims_timestamp,
                        },
                    }
            physio_reap_path = os.path.join(tempdir_path, reap_name)
            os.mkdir(physio_reap_path)
            for pts, pfn in physio_tuples:
                shutil.copy2(os.path.join(data_path, pfn), physio_reap_path)
            reaper.create_archive(os.path.join(reap_path, reap_name+'.tgz'), physio_reap_path, reap_name, metadata, compresslevel=6)
    else:
        log.info('periph data  %s %s not found' % (log_info, name))
