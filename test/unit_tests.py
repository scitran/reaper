import datetime
import os
import shutil
import tempfile

import pytest

from reaper.eeg_reaper import EEGReaper, EEGFile, EEGFileError


@pytest.yield_fixture(scope='module')
def reaper():
    tmp = tempfile.mkdtemp()
    reaper = EEGReaper({'path': tmp, 'opt_in': None, 'opt_out': None, 'map_key': None})
    yield reaper
    shutil.rmtree(tmp)


@pytest.fixture(scope='function', params=[
    # filepath,                      sort info
    ('not_enough.eeg',               EEGFileError('cannot infer sorting info')),
    ('g_p_sub_sess.eeg',             ('g', 'p', 'sub', 'sess')),
    ('g_p_sub_sess_acq.eeg',         ('g', 'p', 'sub', 'sess', 'acq')),
    ('g/p_sub_sess_acq.eeg',         ('g', 'p', 'sub', 'sess', 'acq')),
    ('g/p/sub_sess_acq.eeg',         ('g', 'p', 'sub', 'sess', 'acq')),
    ('g/p/sub/sess_acq.eeg',         ('g', 'p', 'sub', 'sess', 'acq')),
    ('g/p/sub/sess/acq.eeg',         ('g', 'p', 'sub', 'sess', 'acq')),
    ('g_under/p/sub/sess/acq.eeg',   ('g_under', 'p', 'sub', 'sess', 'acq')),
    ('ignored_g_p_sub_sess_acq.eeg', ('g', 'p', 'sub', 'sess', 'acq')),
    ('ignored/g/p/sub/sess/acq.eeg', ('g', 'p', 'sub', 'sess', 'acq')),
])
def testdata(reaper, request):
    filepath, expected_sort_info = request.param
    filepath = reaper.path + '/' + filepath
    if not os.path.exists(os.path.dirname(filepath)):
        os.makedirs(os.path.dirname(filepath))
    open(filepath, 'w').close()
    open(filepath.replace('.eeg', '.vhdr'), 'w').close()
    if not isinstance(expected_sort_info, Exception) and len(expected_sort_info) < 5:
        expected_sort_info += (datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S'),)
    return filepath, expected_sort_info


def test_eeg_reaper(reaper, testdata, tmpdir):
    filepath, expected_sort_info = testdata

    if isinstance(expected_sort_info, Exception):
        with pytest.raises(type(expected_sort_info)) as exc_info:
            eeg = EEGFile(filepath, reaper.path)
        assert str(expected_sort_info) in str(exc_info.value)

    else:
        eeg = EEGFile(filepath, reaper.path)
        assert eeg.group__id       == expected_sort_info[0]
        assert eeg.project_label   == expected_sort_info[1]
        assert eeg.subject_code    == expected_sort_info[2]
        assert eeg.session_uid     == expected_sort_info[3]
        assert eeg.acquisition_uid == expected_sort_info[4]

        _id = eeg.acquisition_uid

        query = reaper.instrument_query()
        assert _id in query
        item = query[_id]

        reaped, metadata_map = reaper.reap(_id, item, tmpdir.strpath)
        assert reaped
