"""SciTran Folder Uploader"""

import os
import sys
import json
import logging
import argparse

from . import util
from . import tempdir as tempfile

logging.basicConfig(
    format='%(asctime)s %(levelname)8.8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
log = logging.getLogger()

OAUTH_TOKEN_VAR = 'SCITRAN_REAPER_OAUTH_TOKEN'

with open(os.path.join(os.path.dirname(__file__), 'types.json')) as fd:
    TYPE_MAP = json.load(fd)
KNOWN_FILETYPES = {ext: filetype for filetype, extensions in TYPE_MAP.iteritems() for ext in extensions}


def guess_filetype(path):
    # pylint: disable=missing-docstring
    particles = os.path.basename(path).split('.')[1:]
    extentions = ['.' + '.'.join(particles[i:]) for i in range(len(particles))]
    for ext in extentions:
        filetype = KNOWN_FILETYPES.get(ext.lower())
        if filetype:
            break
    else:
        filetype = None
    return filetype


def scan_folder(path):
    # pylint: disable=missing-docstring
    projects = []
    for dirpath, dirnames, filenames in os.walk(path):
        filenames = [fn for fn in filenames if not fn.startswith('.')]      # ignore dotfiles
        dirnames[:] = [dn for dn in dirnames if not dn.startswith('.')]     # use slice assignment to influence walk
        relpath = os.path.relpath(dirpath, path)
        if relpath == '.':
            continue
        levels = relpath.split(os.sep)
        level_cnt = len(levels)
        files = []
        if level_cnt == 1:      # group
            if filenames:
                log.critical('Files not allowed at group level')
                sys.exit(1)
        elif level_cnt == 2:    # project
            sessions = []
            files = [{'path': os.path.join(dirpath, fn)} for fn in filenames]
            project = {'group': levels[0], 'label': levels[1], 'sessions': sessions, 'files': files}
            projects.append(project)
        elif level_cnt == 3:    # subject
            if filenames:
                log.critical('Files not allowed at subject level')
                sys.exit(1)
        elif level_cnt == 4:    # session
            acquisitions = []
            files = [{'path': os.path.join(dirpath, fn)} for fn in filenames]
            session = {'label': levels[3], 'subject': {'code': levels[2]}, 'acquisitions': acquisitions, 'files': files}
            sessions.append(session)
        elif level_cnt == 5:    # acquisition
            files = [{'path': os.path.join(dirpath, fn)} for fn in filenames]
            packfiles = [{'path': os.path.join(dirpath, dn), 'type': dn} for dn in dirnames]
            acquisition = {'label': levels[4], 'files': files, 'packfiles': packfiles}
            acquisitions.append(acquisition)
        elif level_cnt == 6:    # packfile
            pass
        else:
            log.critical('Folder structure too deep')
            sys.exit(1)
        for f in files:
            f['type'] = guess_filetype(f['path'])
    return projects


def tweak_labels(projects):
    # pylint: disable=missing-docstring
    for proj in projects:
        session_labels = [sess['label'] for sess in proj['sessions']]
        if len(set(session_labels)) < len(session_labels):
            for sess in proj['sessions']:
                sess['label'] = sess['subject']['code'] + '_' + sess['label']
    return projects


def print_upload_summary(projects):
    # pylint: disable=missing-docstring,unused-argument
    pass


def file_metadata(f, **kwargs):
    # pylint: disable=missing-docstring
    md = {'name': os.path.basename(f['path'])}
    if f['type'] is not None:
        md['type'] = f['type']
    md.update(kwargs)
    return md


def upload(projects, url, request_session):
    # pylint: disable=missing-docstring
    upload_url = url + '/upload/label'
    action_str = 'Upserting %sfiles to %s'
    file_str = '  %s %-10.10s: %s'

    for project in projects:
        group = project['group']
        p_label = group + ' > ' + project['label']
        metadata = {'group': {'_id': group}, 'project': {'label': project['label']}}
        log.info('Upserting group ' + group)
        r = request_session.post(url + '/groups', json={'_id': group.lower(), 'name': group})
        if not r.ok:
            log.error('Failed to upsert group ' + group + '. Trying to proceed anyway.')
        log.info(action_str, '', p_label)
        for f in project['files']:
            log.info(file_str, 'Uploading', f['type'], f['path'])
            metadata['project']['files'] = [file_metadata(f)]
            util.http_upload(request_session, upload_url, f['path'], metadata)
        metadata['project'].pop('files', [])
        for session in project['sessions']:
            s_label = p_label + ' > ' + session['label']
            log.info(action_str, '', s_label)
            metadata.update({'session': {'label': session['label'], 'subject': session['subject']}})
            for f in session['files']:
                log.info(file_str, 'Uploading', f['type'], f['path'])
                metadata['session']['files'] = [file_metadata(f)]
                util.http_upload(request_session, upload_url, f['path'], metadata)
            metadata['session'].pop('files', [])
            for acquisition in session['acquisitions']:
                a_label = s_label + ' > ' + acquisition['label']
                log.info(action_str, '', a_label)
                metadata.update({'acquisition': {'label': acquisition['label']}})
                for f in acquisition['files']:
                    log.info(file_str, 'Uploading', f['type'], f['path'])
                    metadata['acquisition']['files'] = [file_metadata(f)]
                    util.http_upload(request_session, upload_url, f['path'], metadata)
                metadata['acquisition'].pop('files', [])
                log.info(action_str, 'pack-', a_label)
                for f in acquisition['packfiles']:
                    with tempfile.TemporaryDirectory() as tempdir:
                        log.info(file_str, 'Packaging', f['type'], f['path'])
                        arcname = acquisition['label'] + '_' + f['type']
                        fp = util.create_archive(f['path'], arcname, metadata, tempdir)
                        metadata['acquisition']['files'] = [file_metadata(f, name=os.path.basename(fp))]
                        log.info(file_str, 'Uploading', f['type'], f['path'])
                        util.http_upload(request_session, upload_url, fp, metadata)
                metadata['acquisition'].pop('files', [])


def main():
    # pylint: disable=missing-docstring
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('url', help='API URL')
    arg_parser.add_argument('path', help='path to reap')
    arg_parser.add_argument('-i', '--insecure', action='store_true', help='do not verify server SSL certificates')
    arg_parser.add_argument('-u', '--unattended', action='store_true', help='do not stop for user confirmation')
    arg_parser.add_argument('-l', '--loglevel', default='info', help='log level [INFO]')

    auth_group = arg_parser.add_mutually_exclusive_group(required=False)
    auth_group.add_argument('--oauth', action='store_true', help='read OAuth token from ' + OAUTH_TOKEN_VAR)
    auth_group.add_argument('--secret', help='shared API secret')
    arg_parser.add_argument('--root', action='store_true', help='send API requests as site admin')

    args = arg_parser.parse_args()
    args.url = args.url.strip('/')

    log.setLevel(getattr(logging, args.loglevel.upper()))
    log.debug(args)

    if args.oauth:
        auth_token = os.environ.get(OAUTH_TOKEN_VAR)
        if not auth_token:
            log.critical(OAUTH_TOKEN_VAR + ' empty or undefined')
            sys.exit(1)

    log.info('Inspecting  %s', args.path)
    projects = scan_folder(args.path)
    projects = tweak_labels(projects)
    if not args.unattended:
        print_upload_summary(projects)
        # wait for user confirmation

    rs = util.request_session(('importer', 'admin import'), args.root, args.secret, auth_token, args.insecure)
    try:
        upload(projects, args.url, rs)
    # pylint: disable=broad-except
    except Exception as ex:
        log.critical(str(ex))
        sys.exit(1)
