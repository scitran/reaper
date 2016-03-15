import os
import json
import pytz
import zipfile
import calendar
import datetime
import dateutil.parser
import requests_toolbelt


def hrsize(size):
    if size < 1000:
        return '%d%s' % (size, 'B')
    for suffix in 'KMGTPEZY':
        size /= 1024.
        if size < 10.:
            return '%.1f%sB' % (size, suffix)
        if size < 1000.:
            return '%.0f%sB' % (size, suffix)
    return '%.0f%sB' % (size, 'Y')


def metadata_encoder(o):
    if isinstance(o, datetime.datetime):
        # TODO do we need this check or will isoformat take care of it?
        if o.tzinfo is None:
            o = pytz.timezone('UTC').localize(o)
        return o.isoformat()
    elif isinstance(o, datetime.tzinfo):
        return o.zone
    raise TypeError(repr(o) + ' is not JSON serializable')


def datetime_encoder(o):
    if isinstance(o, datetime.datetime):
        return {"$isotimestamp": o.isoformat()}
    raise TypeError(repr(o) + " is not JSON serializable")


def datetime_decoder(dct):
    if "$isotimestamp" in dct:
        return dateutil.parser.parse(dct['$isotimestamp'])
    return dct


def create_archive(content, arcname, metadata, outdir=None, filenames=None):
    path = (os.path.join(outdir, arcname) if outdir else os.path.join(os.path.dirname(content), arcname)) + '.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        zf.comment = json.dumps(metadata, default=metadata_encoder)
        for fn in filenames or os.listdir(content):
            zf.write(os.path.join(content, fn), os.path.join(arcname, fn))
    return path


def localize_timestamp(timestamp, timezone):
    return timezone.localize(timestamp)


def upload_file(rs, url, filepath, metadata):
    filename = os.path.basename(filepath)
    metadata_json = json.dumps(metadata, default=metadata_encoder)
    with open(filepath, 'rb') as fd:
        mpe = requests_toolbelt.multipart.encoder.MultipartEncoder(fields={'metadata': metadata_json, 'file': (filename, fd)})
        r = rs.post(url, data=mpe, headers={'Content-Type': mpe.content_type})
        if not r.ok:
            raise Exception(str(r.status_code) + ' ' + r.reason)
