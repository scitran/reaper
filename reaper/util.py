import os
import json
import zipfile
import calendar
import datetime


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
        if o.tzinfo is None:
            o = pytz.timezone('UTC').localize(o)
        return o.isoformat()
    elif isinstance(o, datetime.tzinfo):
        return o.zone
    raise TypeError(repr(o) + ' is not JSON serializable')


def datetime_encoder(o):
    if isinstance(o, datetime.datetime):
        if o.utcoffset() is not None:
            o = o - o.utcoffset()
        return {"$date": int(calendar.timegm(o.timetuple()) * 1000 + o.microsecond / 1000)}
    raise TypeError(repr(o) + " is not JSON serializable")


def datetime_decoder(dct):
    if "$date" in dct:
        return datetime.datetime.utcfromtimestamp(float(dct["$date"]) / 1000.0)
    return dct


def create_archive(content, arcname, metadata):
    path = content + '.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        zf.comment = json.dumps(metadata, default=metadata_encoder)
        zf.write(content, arcname)
        for fn in os.listdir(content):
            zf.write(os.path.join(content, fn), os.path.join(arcname, fn))
    return path


def localize_timestamp(timestamp, timezone):
    return timezone.localize(timestamp)
