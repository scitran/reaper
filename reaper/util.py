"""SciTran Reaper utility functions"""

import os
import json
import logging
import zipfile
import datetime

import pytz
import tzlocal
import requests
import dateutil.parser
import requests_toolbelt

logging.basicConfig(
    format='%(asctime)s %(name)16.16s:%(levelname)4.4s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO,
)
log = logging.getLogger(__name__)
logging.getLogger('requests').setLevel(logging.WARNING)


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
        log.warning('state file not found')
        state = {}
    except ValueError:
        log.warning('state file corrupt')
        state = {}
    return state


def write_state_file(path, state):
    # pylint: disable=missing-docstring
    temp_path = '/.'.join(os.path.split(path))
    with open(temp_path, 'w') as fd:
        json.dump(state, fd, indent=4, separators=(',', ': '), default=datetime_encoder)
        fd.write('\n')
    os.rename(temp_path, path)


def create_archive(content, arcname, metadata, outdir=None):
    # pylint: disable=missing-docstring
    path = (os.path.join(outdir, arcname) if outdir else os.path.join(os.path.dirname(content), arcname)) + '.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        zf.comment = json.dumps(metadata, default=metadata_encoder)
        files = [(fn, os.path.join(content, fn)) for fn in os.listdir(content)]
        files.sort(key=lambda f: os.path.getsize(f[1]))
        for fn, fp in files:
            zf.write(fp, os.path.join(arcname, fn))
    return path


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


def uri_upload_function(uri, client_info, root=False, secret=None, auth_token=None, insecure=False):
    # pylint: disable=missing-docstring
    """Helper to get an appropriate upload function based on protocol"""
    if uri.startswith('http://') or uri.startswith('https://'):
        uri, _, secret = uri.partition('?secret=')
        rs = request_session(client_info, root, secret, auth_token, insecure)
        return http_upload, uri, rs
    elif uri.startswith('s3://'):
        return s3_upload, None, None
    elif uri.startswith('file://'):
        return file_copy, None, None
    else:
        raise ValueError('bad upload URI "%s"' % uri)


def http_upload(rs, uri, filepath, metadata):
    # pylint: disable=missing-docstring
    filename = os.path.basename(filepath)
    metadata_json = json.dumps(metadata, default=metadata_encoder)
    with open(filepath, 'rb') as fd:
        mpe = requests_toolbelt.multipart.encoder.MultipartEncoder(fields={'metadata': metadata_json, 'file': (filename, fd)})
        r = rs.post(uri, data=mpe, headers={'Content-Type': mpe.content_type})
        if not r.ok:
            raise Exception(str(r.status_code) + ' ' + r.reason)


def request_session(client_info, root=False, secret=None, auth_token=None, insecure=False):
    # pylint: disable=missing-docstring
    if insecure:
        requests.packages.urllib3.disable_warnings()
    rs = requests.Session()
    rs.headers = {
        'X-SciTran-Method': client_info[0],
        'X-SciTran-Name': client_info[1],
    }
    rs.params = {
        'root': root,
    }
    if secret:
        rs.headers['X-SciTran-Auth'] = secret
    elif auth_token:
        rs.headers['Authorization'] = auth_token
    rs.verify = not insecure
    return rs


def s3_upload(self, filename, filepath, metadata, digest, uri):
    # pylint: disable=missing-docstring, unused-argument
    pass


def file_copy(self, filename, filepath, metadata, digest, uri):
    # pylint: disable=missing-docstring, unused-argument
    pass
