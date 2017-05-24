import os

import mock
import pytest

from reaper.eeg_reaper import EEGReaper, EEGFile


@pytest.fixture()
def eeg_data():
    pass


def test_eegfile():
    with mock.patch('os.access'):
        eeg = EEGFile('/group_id/project_label/subject_code/session_uid/000001.eeg')
        assert eeg.group__id == 'group_id'
        assert eeg.project_label == 'project_label'
        assert eeg.subject_code == 'subject_code'
        assert eeg.session_uid == 'session_uid'
