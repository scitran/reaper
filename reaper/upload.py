"""SciTran Reaper upload utility functions"""

import os
import json
import array
import logging
import datetime

import httplib
import requests
import requests_toolbelt

from . import util

log = logging.getLogger(__name__)
logging.getLogger('requests').setLevel(logging.WARNING)


# monkey patching httplib to increase performance due to hard-coded block size
def __fast_http_send(self, data):
    """Send `data' to the server."""
    if self.sock is None:
        if self.auto_open:
            self.connect()
        else:
            raise httplib.NotConnected()

    if self.debuglevel > 0:
        print "send:", repr(data)
    blocksize = 2**20  # was 8192 originally
    if hasattr(data, 'read') and not isinstance(data, array.array):
        if self.debuglevel > 0:
            print "sendIng a read()able"
        datablock = data.read(blocksize)
        while datablock:
            self.sock.sendall(datablock)
            datablock = data.read(blocksize)
    else:
        self.sock.sendall(data)

httplib.HTTPConnection.send = __fast_http_send
httplib.HTTPSConnection.send = __fast_http_send


def upload_many(metadata_map, upload_func):
    # pylint: disable=missing-docstring
    for filepath, metadata in metadata_map.iteritems():
        success = metadata_upload(filepath, metadata, upload_func)
        if not success:
            return False
    return True


def metadata_upload(filepath, metadata, upload_func):
    # pylint: disable=missing-docstring
    filename = os.path.basename(filepath)
    log.warning('Uploading    %s [%s]', filename, util.hrsize(os.path.getsize(filepath)))
    start = datetime.datetime.utcnow()
    success = upload_func(filepath, metadata)
    duration = (datetime.datetime.utcnow() - start).total_seconds()
    if success:
        log.info('Uploaded     %s [%s/s]', filename, util.hrsize(os.path.getsize(filepath) / duration))
    else:
        log.error('Failure      %s', filename)
    return success


def upload_function(uri, secret_info=None, key=None, root=False, insecure=False, upload_route=''):
    # pylint: disable=missing-docstring
    """Helper to get an appropriate upload function based on protocol"""
    if uri.startswith('http://') or uri.startswith('https://'):
        return __http_upload(uri.strip('/'), secret_info, key, root, insecure, upload_route)
    elif uri.startswith('dummy://'):
        return lambda method, route, **kwargs: True, lambda filepath, metadata: True
    elif uri.startswith('s3://'):
        return __s3_upload
    elif uri.startswith('file://'):
        return __file_copy
    else:
        raise ValueError('bad upload URI "%s"' % uri)


def __http_upload(url, secret_info, key, root, insecure, upload_route):
    # pylint: disable=missing-docstring
    http_session = __request_session(secret_info, key, root, insecure)

    def request(method, route, **kwargs):
        try:
            r = http_session.request(method, url + route, **kwargs)
        except requests.exceptions.ConnectionError as ex:
            log.error('Error        %s', ex)
            return False
        if r.ok:
            return True
        else:
            log.error('Failure      %s %s', r.status_code, r.reason)
            return False

    def upload(filepath, metadata):
        filename = os.path.basename(filepath)
        metadata_json = json.dumps(metadata, default=util.metadata_encoder)
        with open(filepath, 'rb') as fd:
            mpe = requests_toolbelt.multipart.encoder.MultipartEncoder(fields={'metadata': metadata_json, 'file': (filename, fd)})
            try:
                r = http_session.post(url + upload_route, data=mpe, headers={'Content-Type': mpe.content_type})
            except requests.exceptions.ConnectionError as ex:
                log.error('Error        %s: %s', filename, ex)
                return False
            if r.ok:
                return True
            else:
                log.error('Failure      %s: %s %s', filename, r.status_code, r.reason)
                return False

    return request, upload


def __request_session(secret_info, key, root, insecure):
    # pylint: disable=missing-docstring
    if insecure:
        requests.urllib3.disable_warnings()
    rs = requests.Session()
    if secret_info:
        rs.headers['X-SciTran-Method'] = secret_info[0]
        rs.headers['X-SciTran-Name'] = secret_info[1]
        rs.headers['X-SciTran-Auth'] = secret_info[2]
    elif key:
        rs.headers['Authorization'] = 'scitran-user ' + key
    rs.params['root'] = root
    rs.verify = not insecure
    return rs


def __s3_upload(filename, filepath, metadata, digest, uri):
    # pylint: disable=missing-docstring, unused-argument
    pass


def __file_copy(filename, filepath, metadata, digest, uri):
    # pylint: disable=missing-docstring, unused-argument
    pass
