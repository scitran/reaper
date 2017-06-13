import datetime
import os
import shutil
import tempfile

import pytest

from reaper.eeg_reaper import EEGReaper, EEGFile


@pytest.yield_fixture(scope='module')
def reaper():
    tmp = tempfile.mkdtemp()
    yield EEGReaper({'path': tmp})
    shutil.rmtree(tmp)


@pytest.fixture(scope='function', params=[
    # filepath                     sort info
    ('not_enough.eeg',             ('', 'not_enough', '', '')),
    ('g_p_sub_sess.eeg',           ('g', 'p', 'sub', 'sess')),
    ('g_p_sub_sess_acq.eeg',       ('g', 'p', 'sub', 'sess', 'acq')),
    ('g/p_sub_sess_acq.eeg',       ('g', 'p', 'sub', 'sess', 'acq')),
    ('g/p/sub_sess_acq.eeg',       ('g', 'p', 'sub', 'sess', 'acq')),
    ('g/p/sub/sess_acq.eeg',       ('g', 'p', 'sub', 'sess', 'acq')),
    ('g/p/sub/sess/acq.eeg',       ('g', 'p', 'sub', 'sess', 'acq')),
    ('g_under/p/sub/sess/acq.eeg', ('g_under', 'p', 'sub', 'sess', 'acq')),
    ('g_p_sub_sess_acq_extra.eeg', ('g', 'p', 'sub', 'sess', 'acq_extra')),
    ('g/p/sub/sess/acq/extra.eeg', ('g', 'p', 'sub', 'sess', 'acq_extra')),
])
def testdata(reaper, request):
    filepath, expected_sort_info = request.param
    filepath = reaper.path + '/' + filepath
    if not os.path.exists(os.path.dirname(filepath)):
        os.makedirs(os.path.dirname(filepath))
    open(filepath, 'w').close()
    open(filepath.replace('.eeg', '.vhdr'), 'w').close()
    if not isinstance(expected_sort_info, Exception) and len(expected_sort_info) < 5:
        expected_sort_info += (datetime.datetime.now(tz=reaper.timezone).strftime('%Y%m%d_%H%M%S'),)
    return filepath, expected_sort_info


def test_eeg_reaper(reaper, testdata, tmpdir):
    filepath, expected_sort_info = testdata

    eeg = EEGFile(filepath, reaper)
    assert eeg.group__id       == expected_sort_info[0]
    assert eeg.project_label   == expected_sort_info[1]
    assert eeg.subject_code    == expected_sort_info[2]
    assert eeg.session_uid     == expected_sort_info[3]
    assert eeg.acquisition_uid == expected_sort_info[4]

    query = reaper.instrument_query()
    assert eeg.reap_id in query
    item = query[eeg.reap_id]

    reaped, metadata_map = reaper.reap(eeg.reap_id, item, tmpdir.strpath)
    assert reaped
