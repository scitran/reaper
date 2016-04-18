import os
import sys
import json
import logging
import argparse
import requests
import requests_toolbelt

from . import util
from . import tempdir as tempfile

logging.basicConfig(
    format='%(asctime)s %(levelname)8.8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

log = logging.getLogger()

logging.getLogger('requests').setLevel(logging.WARNING) # silence Requests library


OAUTH_TOKEN_VAR = 'SCITRAN_REAPER_OAUTH_TOKEN'

with open(os.path.join(os.path.dirname(__file__), 'types.json')) as fd:
    KNOWN_FILETYPES = json.load(fd)


def guess_filetype(path):
    particles = os.path.basename(path).split('.')[1:]
    extentions = ['.' + '.'.join(particles[i:]) for i in range(len(particles))]
    for ext in extentions:
        filetype = KNOWN_FILETYPES.get(ext.lower())
        if filetype:
            break
    return filetype


def scan_folder(path):
    projects = []
    for dirpath, dirnames, filenames in os.walk(path):
        filenames = [fn for fn in filenames if not fn.startswith('.')]  # ignore dotfiles
        dirnames[:] = [dn for dn in dirnames if not dn.startswith('.')] # use slice assignment to influence walk
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
            files = [{'path': os.path.join(dirpath, fn), 'type': None} for fn in filenames]
            project = {'group': levels[0], 'label': levels[1], 'sessions': sessions, 'files': files}
            projects.append(project)
        elif level_cnt == 3:    # subject
            if filenames:
                log.critical('Files not allowed at subject level')
                sys.exit(1)
        elif level_cnt == 4:    # session
            acquisitions = []
            files = [{'path': os.path.join(dirpath, fn), 'type': None} for fn in filenames]
            session = {'label': levels[3], 'subject': {'code': levels[2]}, 'acquisitions': acquisitions, 'files': files}
            sessions.append(session)
        elif level_cnt == 5:    # acquisition
            files = [{'path': os.path.join(dirpath, fn), 'type': None} for fn in filenames]
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
    for p in projects:
        session_labels = [s['label'] for s in p['sessions']]
        if len(set(session_labels)) < len(session_labels):
            for s in p['sessions']:
                s['label'] = s['subject']['code'] + '_' + s['label']
    return projects


def print_upload_summary(projects):
    pass


def file_metadata(f, **kwargs):
    md = {'name': os.path.basename(f['path']), 'type': f['type']}
    md.update(kwargs)
    return md


def upload(projects, api_url, http_headers, http_params, insecure):
    with requests.Session() as rs:
        rs.verify = not insecure
        rs.headers = http_headers
        rs.params = http_params
        upload_url = api_url + '/upload/label'
        action_str = 'Upserting {}files to {}'
        file_str = '  {} {f[type]:10}: {f[path]}'

        for project in projects:
            group = project['group']
            p_label = group + ' > ' + project['label']
            metadata = {'group': { '_id': group}, 'project': { 'label': project['label']}}
            log.info('Upserting group ' + group)
            r = rs.post(api_url + '/groups', json={'_id': group.lower(), 'name': group})
            if not r.ok:
                log.error('Failed to upsert group ' + group + '. Trying to proceed anyway.')
            log.info(action_str.format('', p_label))
            for f in project['files']:
                log.info(file_str.format('Uploading', f=f))
                metadata['project']['files'] = [file_metadata(f)]
                util.upload_file(rs, upload_url, f['path'], metadata)
            metadata['project'].pop('files', [])
            for session in project['sessions']:
                s_label = p_label + ' > ' + session['label']
                log.info(action_str.format('', s_label))
                metadata.update({'session': {'label': session['label'], 'subject': session['subject']}})
                for f in session['files']:
                    log.info(file_str.format('Uploading', f=f))
                    metadata['session']['files'] = [file_metadata(f)]
                    util.upload_file(rs, upload_url, f['path'], metadata)
                metadata['session'].pop('files', [])
                for acquisition in session['acquisitions']:
                    a_label = s_label + ' > ' + acquisition['label']
                    log.info(action_str.format('', a_label))
                    metadata.update({'acquisition': {'label': acquisition['label']}})
                    for f in acquisition['files']:
                        log.info(file_str.format('Uploading', f=f))
                        metadata['acquisition']['files'] = [file_metadata(f)]
                        util.upload_file(rs, upload_url, f['path'], metadata)
                    metadata['acquisition'].pop('files', [])
                    log.info(action_str.format('pack-', a_label))
                    for f in acquisition['packfiles']:
                        with tempfile.TemporaryDirectory() as tempdir:
                            log.info(file_str.format('Packaging', f=f))
                            arcname = acquisition['label'] + '_' + f['type']
                            fp = util.create_archive(f['path'], arcname, metadata, tempdir)
                            metadata['acquisition']['files'] = [file_metadata(f, name=os.path.basename(fp))]
                            log.info(file_str.format('Uploading', f=f))
                            util.upload_file(rs, upload_url, fp, metadata)
                    metadata['acquisition'].pop('files', [])


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument('url', help='API URL')
    arg_parser.add_argument('path', help='path to reap')
    arg_parser.add_argument('-i', '--insecure', action='store_true', help='do not verify server SSL certificates')
    arg_parser.add_argument('-u', '--unattended', action='store_true', help='do not stop for user confirmation')
    arg_parser.add_argument('-l', '--loglevel', default='info', help='log level [INFO]')

    auth_group = arg_parser.add_mutually_exclusive_group(required=False)
    auth_group.add_argument(      '--oauth', action='store_true', help='read OAuth token from ' + OAUTH_TOKEN_VAR)
    auth_group.add_argument(      '--secret', help='shared API secret')
    arg_parser.add_argument(      '--root', action='store_true', help='send API requests as site admin')

    args = arg_parser.parse_args()

    log.setLevel(getattr(logging, args.loglevel.upper()))

    if args.insecure:
        requests.packages.urllib3.disable_warnings()

    args.url = args.url.strip('/')

    http_headers = {
        'X-SciTran-Method': 'importer',
        'X-SciTran-Name': 'Admin Import',
    }
    if args.secret:
        http_headers['X-SciTran-Auth'] = args.secret
    elif args.oauth:
        http_headers['Authorization'] = os.environ.get(OAUTH_TOKEN_VAR)
        if not http_headers['Authorization']:
            log.critical(OAUTH_TOKEN_VAR + ' empty or undefined')
            sys.exit()

    http_params = {}
    if args.root:
        http_params['root'] = 'true'

    log.debug(args)

    log.info('Inspecting  %s' % args.path)
    projects = scan_folder(args.path)
    projects = tweak_labels(projects)
    if not args.unattended:
        print_upload_summary(projects)
        # wait for user confirmation

    try:
        upload(projects, args.url, http_headers, http_params, args.insecure)
    except Exception as e:
        log.critical(str(e))
        sys.exit(1)
