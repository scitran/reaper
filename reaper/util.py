"""SciTran Reaper utility functions"""

import os
import json
import shutil
import string
import logging
import zipfile
import datetime

import pytz
import tzlocal
import dateutil.parser

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
    ('subject', 'sex'),
    ('subject', 'age'),
    ('acquisition', 'instrument'),
    ('acquisition', 'measurement'),
    ('file', 'instrument'),
    ('file', 'measurements'),
]

log = logging.getLogger(__name__)


def hrsize(size):
    # pylint: disable=missing-docstring
    if size < 1000:
        return '%d%s' % (size, 'B')
    for suffix in 'KMGTPEZY':
        size /= 1024.
        if size < 10.:
            return '%.1f%sB' % (size, suffix)
        if size < 1000.:
            return '%.0f%sB' % (size, suffix)
    return '%.0f%sB' % (size, 'Y')


def object_metadata(obj, timezone, filename):
    # pylint: disable=missing-docstring
    metadata = {
        'session': {'timezone': timezone},
        'acquisition': {'timezone': timezone},
    }
    for md_group, md_field in METADATA:
        value = getattr(obj, md_group + '_' + md_field, None)
        if value is not None:
            metadata.setdefault(md_group, {})
            metadata[md_group][md_field] = value
    metadata['file']['name'] = filename
    metadata['session']['subject'] = metadata.pop('subject', {})
    metadata['acquisition']['files'] = [metadata.pop('file', {})]
    return metadata


def metadata_encoder(obj):
    # pylint: disable=missing-docstring
    if isinstance(obj, datetime.datetime):
        if obj.tzinfo is None:
            obj = pytz.timezone('UTC').localize(obj)
        return obj.isoformat()
    elif isinstance(obj, datetime.tzinfo):
        return obj.zone
    raise TypeError(repr(obj) + ' is not JSON serializable')


def datetime_encoder(obj):
    # pylint: disable=missing-docstring
    if isinstance(obj, datetime.datetime):
        return {"$isotimestamp": obj.isoformat()}
    raise TypeError(repr(obj) + " is not JSON serializable")


def datetime_decoder(dct):
    # pylint: disable=missing-docstring
    if "$isotimestamp" in dct:
        return dateutil.parser.parse(dct['$isotimestamp'])
    return dct


def read_state_file(path):
    # pylint: disable=missing-docstring
    try:
        with open(path, 'r') as fd:
            state = json.load(fd, object_hook=datetime_decoder)
        # TODO add some consistency checks here and possibly drop state if corrupt
    except IOError:
        log.warning('State file not found')
        state = {}
    except ValueError:
        log.warning('State file corrupt')
        state = {}
    return state


def write_state_file(path, state):
    # pylint: disable=missing-docstring
    temp_path = '/.'.join(os.path.split(path))
    with open(temp_path, 'w') as fd:
        json.dump(state, fd, indent=4, separators=(',', ': '), default=datetime_encoder)
        fd.write('\n')
    shutil.move(temp_path, path)


def create_archive(content, arcname, metadata=None, outdir=None):
    # pylint: disable=missing-docstring
    if hasattr(content, '__iter__'):
        outdir = outdir or os.path.curdir
        files = [(os.path.basename(fp), fp) for fp in content]
    else:
        outdir = outdir or os.path.dirname(content)
        files = [(fn, os.path.join(content, fn)) for fn in os.listdir(content)]
    outpath = os.path.join(outdir, arcname) + '.zip'
    files.sort(key=lambda f: os.path.getsize(f[1]))
    with zipfile.ZipFile(outpath, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        if metadata is not None:
            zf.comment = json.dumps(metadata, default=metadata_encoder)
        for fn, fp in files:
            zf.write(fp, os.path.join(arcname, fn))
    return outpath


def set_archive_metadata(path, metadata):
    # pylint: disable=missing-docstring
    with zipfile.ZipFile(path, 'a', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        zf.comment = json.dumps(metadata, default=metadata_encoder)


def validate_timezone(zone):
    # pylint: disable=missing-docstring
    if zone is None:
        zone = tzlocal.get_localzone()
    else:
        try:
            zone = pytz.timezone(zone)
        except pytz.UnknownTimeZoneError:
            zone = None
    return zone


def localize_timestamp(timestamp, timezone):
    # pylint: disable=missing-docstring
    return timezone.localize(timestamp)


def parse_sorting_info(sort_info, default_subj_code):
    """
    Parse subject code, group name and project name from an id.

    If the id does not contain a subject code, rely on the supplied default.

    Expected formatting: subj_code@group_name/project_name

    Parameters
    ----------
    sort_info : str
        sort_info string from data
    default_subj_code : str
        subject code to use if sort_info does not contain a subject code

    Returns
    -------
    subj_code : str
        string of subject identifer
    group_name : str
        string of group name
    project_name : str
        string of project name

    """
    subj_code = group_name = exp_name = None
    if sort_info is not None:
        subj_code, _, lab_info = sort_info.strip(string.punctuation + string.whitespace).rpartition('@')
        group_name, _, exp_name = lab_info.partition('/')
    return subj_code or default_subj_code, group_name, exp_name
