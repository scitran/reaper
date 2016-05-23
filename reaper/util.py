"""SciTran Reaper utility functions"""

import os
import json
import zipfile
import datetime

import pytz
import dateutil.parser
import requests_toolbelt


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


def localize_timestamp(timestamp, timezone):
    # pylint: disable=missing-docstring
    return timezone.localize(timestamp)


def upload_file(rs, url, filepath, metadata):
    # pylint: disable=missing-docstring
    filename = os.path.basename(filepath)
    metadata_json = json.dumps(metadata, default=metadata_encoder)
    with open(filepath, 'rb') as fd:
        mpe = requests_toolbelt.multipart.encoder.MultipartEncoder(fields={'metadata': metadata_json, 'file': (filename, fd)})
        r = rs.post(url, data=mpe, headers={'Content-Type': mpe.content_type})
        if not r.ok:
            raise Exception(str(r.status_code) + ' ' + r.reason)
