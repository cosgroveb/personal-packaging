#!/usr/bin/env python3
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MAPPING = {'bookworm': 'debian', 'trixie': 'debian', 'sid': 'debian', 'noble': 'ubuntu'}


def distributions(token):
    auth = base64.b64encode((token + ':').encode()).decode()
    request = urllib.request.Request('https://packagecloud.io/api/v1/distributions.json', headers={'Authorization': 'Basic ' + auth})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    destination = os.environ.get('PACKAGECLOUD_REPOSITORY', '')
    token = os.environ.get('PACKAGECLOUD_TOKEN', '')
    if not re.fullmatch(r'cosgroveb/[A-Za-z0-9][A-Za-z0-9_.-]*', destination):
        raise ValueError('set PACKAGECLOUD_REPOSITORY to cosgroveb/<repository>')
    if not token:
        raise ValueError('PACKAGECLOUD_TOKEN is required')
    if not shutil.which('package_cloud'):
        raise ValueError('package_cloud CLI is required')
    subprocess.run([str(ROOT / 'scripts/validate-artifacts'), str(ROOT / 'dist')], check=True)
    data = distributions(token)
    available = {(d['index_name'], v['index_name']) for d in data['deb'] for v in d['versions']}
    missing = [(distro, suite) for suite, distro in MAPPING.items() if (distro, suite) not in available]
    if missing:
        raise ValueError(f'Packagecloud does not list required distributions: {missing}')
    jobs = [(f'{destination}/{distro}/{suite}', ROOT / 'dist' / f'live-serve_0.4.3-1_{suite}_{arch}.deb')
            for suite, distro in MAPPING.items() for arch in ('amd64', 'arm64')]
    successes = []
    for index, (target, package) in enumerate(jobs):
        print(f'Uploading {package.name} to {target}', flush=True)
        try:
            result = subprocess.run(['package_cloud', 'push', target, str(package)])
            status = result.returncode
            error = ''
        except OSError as failure:
            status = 1
            error = f': {failure}'
        if status:
            remaining = [f'{dest}: {pkg.name}' for dest, pkg in jobs[index + 1:]]
            print(f'Upload failed for {package.name} to {target}{error}; prior successes: {successes}; unattempted: {remaining}', file=sys.stderr)
            return status
        successes.append(f'{target}: {package.name}')
        print(f'Uploaded {successes[-1]}', flush=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError, urllib.error.URLError, subprocess.CalledProcessError) as error:
        print(f'Publication stopped before upload: {error}', file=sys.stderr)
        sys.exit(1)
