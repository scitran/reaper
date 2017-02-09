"""SciTran Reaper upload utility functions"""

import os
import json
import array
import logging
import httplib
import datetime

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


def upload_many(metadata_map, upload_functions):
    # pylint: disable=missing-docstring
    for filepath, metadata in metadata_map.iteritems():
        for upload_func in upload_functions:
            success = metadata_upload(filepath, metadata, upload_func)
            if not success:
                return False
    return True


def metadata_upload(filepath, metadata, upload_func):
    # pylint: disable=missing-docstring
    filename = os.path.basename(filepath)
    log.debug('Uploading    %s [%s]', filename, util.hrsize(os.path.getsize(filepath)))
    start = datetime.datetime.utcnow()
    success = upload_func(filepath, metadata)
    duration = (datetime.datetime.utcnow() - start).total_seconds()
    if success:
        log.info('Uploaded     %s [%s/s]', filename, util.hrsize(os.path.getsize(filepath) / duration))
    else:
        log.info('Failure      %s', filename)
    return success


def upload_function(uri, client_info, root=False, auth_token=None, insecure=False, upload_route=''):
    # pylint: disable=missing-docstring
    """Helper to get an appropriate upload function based on protocol"""
    if uri.startswith('http://') or uri.startswith('https://'):
        uri, _, secret = uri.partition('?secret=')
        return __http_upload(uri.strip('/'), client_info, root, secret, auth_token, insecure, upload_route)
    elif uri.startswith('testing://'):
        return lambda method, route, **kwargs: True, lambda filepath, metadata: True
    elif uri.startswith('s3://'):
        return __s3_upload
    elif uri.startswith('file://'):
        return __file_copy
    else:
        raise ValueError('bad upload URI "%s"' % uri)


def __request_session(client_info, root=False, secret=None, auth_token=None, insecure=False):
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


def __http_upload(url, client_info, root, secret, auth_token, insecure, upload_route):
    # pylint: disable=missing-docstring
    http_session = __request_session(client_info, root, secret, auth_token, insecure)

    def request(method, route, **kwargs):
        try:
            r = http_session.request(method, url + route, **kwargs)
        except requests.exceptions.ConnectionError as ex:
            log.error('error        %s', ex)
            return False
        if r.ok:
            return True
        else:
            log.warning('failure      %s %s', r.status_code, r.reason)
            return False

    def upload(filepath, metadata):
        filename = os.path.basename(filepath)
        metadata_json = json.dumps(metadata, default=util.metadata_encoder)
        with open(filepath, 'rb') as fd:
            mpe = requests_toolbelt.multipart.encoder.MultipartEncoder(fields={'metadata': metadata_json, 'file': (filename, fd)})
            try:
                r = http_session.post(url + upload_route, data=mpe, headers={'Content-Type': mpe.content_type})
            except requests.exceptions.ConnectionError as ex:
                log.error('error        %s: %s', filename, ex)
                return False
            if r.ok:
                return True
            else:
                log.warning('failure      %s: %s %s', filename, r.status_code, r.reason)
                return False

    return request, upload


def __s3_upload(filename, filepath, metadata, digest, uri):
    # pylint: disable=missing-docstring, unused-argument
    pass


def __file_copy(filename, filepath, metadata, digest, uri):
    # pylint: disable=missing-docstring, unused-argument
    pass
