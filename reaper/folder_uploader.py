"""SciTran Folder Uploader"""

import os
import sys
import json
import logging
import argparse

from . import util
from . import upload
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


def scan_folder(path, symlinks=False):
    # pylint: disable=missing-docstring
    projects = []
    for dirpath, dirnames, filenames in os.walk(path, followlinks=symlinks):
        filenames = [fn for fn in filenames if not fn.startswith('.')]      # ignore dotfiles
        dirnames[:] = [dn for dn in dirnames if not dn.startswith('.')]     # use slice assignment to influence walk
        if dirpath == path:     # skip over top-level directory
            continue
        levels = os.path.relpath(dirpath, path).split(os.sep)
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
    # pylint: disable=missing-docstring
    group_cnt = len(set([proj['group'] for proj in projects]))
    project_cnt = len(projects)
    session_cnt = sum([len(proj['sessions']) for proj in projects])
    log.info('Found %d Session(s) in %d Project(s) in %d Group(s)', session_cnt, project_cnt, group_cnt)


def file_metadata(f, **kwargs):
    # pylint: disable=missing-docstring
    md = {'name': os.path.basename(f['path'])}
    if f['type'] is not None:
        md['type'] = f['type']
    md.update(kwargs)
    return md


def process(projects, upload_func):
    # pylint: disable=missing-docstring
    action_str = 'Upserting %sfiles to %s'
    file_str = '  %s %-10.10s: %s'

    for project in projects:
        group = project['group']
        p_label = group + ' > ' + project['label']
        metadata = {'group': {'_id': group}, 'project': {'label': project['label']}}
        log.info(action_str, '', p_label)
        for f in project['files']:
            log.info(file_str, 'Uploading', f['type'], f['path'])
            metadata['project']['files'] = [file_metadata(f)]
            upload_func(f['path'], metadata)
        metadata['project'].pop('files', [])
        for session in project['sessions']:
            s_label = p_label + ' > ' + session['label']
            log.info(action_str, '', s_label)
            metadata.update({'session': {'label': session['label'], 'subject': session['subject']}})
            for f in session['files']:
                log.info(file_str, 'Uploading', f['type'], f['path'])
                metadata['session']['files'] = [file_metadata(f)]
                upload_func(f['path'], metadata)
            metadata['session'].pop('files', [])
            for acquisition in session['acquisitions']:
                a_label = s_label + ' > ' + acquisition['label']
                log.info(action_str, '', a_label)
                metadata.update({'acquisition': {'label': acquisition['label']}})
                for f in acquisition['files']:
                    log.info(file_str, 'Uploading', f['type'], f['path'])
                    metadata['acquisition']['files'] = [file_metadata(f)]
                    upload_func(f['path'], metadata)
                metadata['acquisition'].pop('files', [])
                log.info(action_str, 'pack-', a_label)
                for f in acquisition['packfiles']:
                    with tempfile.TemporaryDirectory() as tempdir:
                        log.info(file_str, 'Packaging', f['type'], f['path'])
                        arcname = acquisition['label'] + '.' + f['type']
                        fp = util.create_archive(f['path'], arcname, None, tempdir)
                        metadata['acquisition']['files'] = [file_metadata(f, name=os.path.basename(fp))]
                        log.info(file_str, 'Uploading', f['type'], f['path'])
                        upload_func(fp, metadata)
                metadata['acquisition'].pop('files', [])


def main():
    # pylint: disable=missing-docstring
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('path', help='path to reap')
    arg_parser.add_argument('uri', help='API URL')
    arg_parser.add_argument('-i', '--insecure', action='store_true', help='do not verify server SSL certificates')
    arg_parser.add_argument('-y', '--yes', action='store_true', help='do not prompt to continue')
    arg_parser.add_argument('-l', '--loglevel', default='info', help='log level [INFO]')
    arg_parser.add_argument('-s', '--symlinks', action='store_true', help='follow symbolic links that resolve to directories')
    arg_parser.add_argument('--oauth', action='store_true', help='read OAuth token from ' + OAUTH_TOKEN_VAR)
    arg_parser.add_argument('--root', action='store_true', help='send API requests as site admin')

    args = arg_parser.parse_args()
    args.uri = args.uri.strip('/')

    log.setLevel(getattr(logging, args.loglevel.upper()))
    log.debug(args)

    if args.oauth:
        auth_token = os.environ.get(OAUTH_TOKEN_VAR)
        if not auth_token:
            log.critical(OAUTH_TOKEN_VAR + ' empty or undefined')
            sys.exit(1)
    else:
        auth_token = None

    log.info('Inspecting  %s', args.path)
    projects = scan_folder(args.path, args.symlinks)
    projects = tweak_labels(projects)
    if not args.yes:
        print_upload_summary(projects)
        try:
            raw_input('\nPress Enter to process and upload all data or Ctrl-C to abort...')
        except KeyboardInterrupt:
            print
            sys.exit(1)

    upload_func = upload.upload_function(args.uri, ('importer', 'admin import'), args.root, auth_token, args.insecure)
    try:
        process(projects, upload_func)
    # pylint: disable=broad-except
    except Exception as ex:
        log.critical(str(ex))
        sys.exit(1)
