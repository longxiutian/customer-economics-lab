"""Read-only, allowlisted file observations. No workflow imports or analysis execution.

Can be copied outside a frozen release for historical backfill. Credentials are
read from the operator's existing config; no credentials or learner text are output.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

RUN = re.compile(r'^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$')
CATALOG = Path(__file__).with_name('file-catalog.json')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_file(root, path):
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        return False
    return not any(p.is_symlink() for p in (path, *path.parents) if p == root or root in p.parents)


def database_scan(workspace):
    found, visited, complete = 0, 0, True
    for directory, dirs, files in os.walk(workspace, followlinks=False):
        current = Path(directory)
        safe_dirs = [d for d in dirs if not (current / d).is_symlink()]
        if len(safe_dirs) != len(dirs):
            complete = False
        dirs[:] = safe_dirs
        if len(current.relative_to(workspace).parts) >= 6 and dirs:
            dirs[:] = []
            complete = False
        visited += len(files) + len(dirs)
        if visited > 5000:
            complete = False
            break
        found += sum(name.endswith(('.duckdb', '.duckdb.wal', '.db', '.sqlite')) for name in files)
    return {'found': found, 'complete': complete}


def build_manifest(source, workspace, *, session_id, store_id, mode='post_step', catalog_path=CATALOG, paths_disclosable=False):
    if paths_disclosable is not True:
        raise ValueError('Operator has not attested that these paths are disclosable')
    source, workspace = Path(source).absolute(), Path(workspace).absolute()
    if not RUN.fullmatch(workspace.name) or workspace.parent.name != 'workspaces':
        raise ValueError('Invalid workspace root')
    if source.is_symlink() or workspace.is_symlink() or workspace.resolve() != workspace:
        raise ValueError('Symlink workspace roots are not publishable')
    catalog = json.loads(Path(catalog_path).read_text(encoding='utf-8'))
    release = json.loads((workspace / 'release.json').read_text(encoding='utf-8'))
    fingerprint = hashlib.sha256(json.dumps({'inputs':release['inputs'],'implementation':release['implementation']},
                                            sort_keys=True,separators=(',', ':')).encode()).hexdigest()
    if fingerprint != release['release_hash']:
        raise ValueError('Saved release manifest is not intact')
    # The broker owns the reviewed release registry. Keeping that registry out
    # of the hashed source avoids a circular fingerprint for future releases.
    entries = []
    for group in catalog['groups']:
        root = source if group['root'] == 'source' else workspace
        candidates = [root / rel for rel in group.get('rels', [])]
        if group.get('prefix'):
            directory = root / group['prefix']
            if directory.is_dir() and not directory.is_symlink():
                candidates += sorted(directory.glob('*' + group['ext']))[:160]
        for path in candidates:
            if not safe_file(root, path):
                continue
            rel = path.relative_to(root).as_posix()
            digest = sha(path)
            if group['root'] == 'source':
                expected = (release['inputs']['hashes'].get(path.name) if rel.startswith('data/') else release['implementation'].get(rel))
                if expected is None:
                    continue
                if expected != digest:
                    raise ValueError('Frozen source hash mismatch: ' + rel)
            entries.append({'root': group['root'], 'rel': rel, 'size': path.stat().st_size, 'sha256': digest})
    if len(entries) > 240:
        raise ValueError('File observation exceeds bounded catalog')
    audit = workspace / 'lesson/analysis_manifest.json'
    version = json.loads(audit.read_text(encoding='utf-8')).get('duckdb_version') if safe_file(workspace, audit) else None
    return {'schema': 'studio-north.file-manifest/1', 'run_id': workspace.name, 'release_hash': release['release_hash'],
            'session_id': session_id, 'store_id': store_id, 'mode': mode, 'paths_disclosable': True,
            'observed_at': int(time.time()), 'roots': {'source': source.as_posix(), 'workspace': workspace.as_posix()},
            'entries': entries, 'duckdb_scan': database_scan(workspace), 'duckdb_version': version}


def publish(config, manifest):
    headers = {'Authorization': 'Bearer ' + config['worker_key'],
               'X-Worker-Id': config['session_id'] + '-file-observer', 'Content-Type': 'application/json'}
    if config.get('sites_service_token'):
        headers['OAI-Sites-Authorization'] = 'Bearer ' + config['sites_service_token']
    request = Request(config['broker_url'].rstrip('/') + '/api/worker/manifest',
                      data=json.dumps(manifest).encode(), headers=headers, method='PUT')
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--catalog', type=Path, default=CATALOG)
    parser.add_argument('--attest-paths-disclosable', action='store_true', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    runtime = args.runtime or Path(config['runtime'])
    store = json.loads((runtime / 'store.json').read_text(encoding='utf-8'))
    if any(store.get(key) != config[key] for key in ('store_id','session_id')):
        raise ValueError('Configured workspace store mismatch')
    if args.run_id and not RUN.fullmatch(args.run_id):
        raise ValueError('Invalid run id')
    workspaces = [runtime / 'workspaces' / args.run_id] if args.run_id else sorted((runtime / 'workspaces').iterdir())
    failed = 0
    for workspace in workspaces:
        if not RUN.fullmatch(workspace.name) or not (workspace / 'release.json').is_file():
            continue
        try:
            manifest = build_manifest(args.source, workspace, session_id=config['session_id'], store_id=config['store_id'],
                                      mode='backfill_readonly', catalog_path=args.catalog, paths_disclosable=args.attest_paths_disclosable)
            if not args.dry_run:
                response = publish(config, manifest)
                if not response.get('applied'):
                    raise ValueError('Observation was not applied; run changed or a newer observation exists')
        except Exception as exc:
            failed += 1
            print(json.dumps({'run_id':workspace.name,'error':getattr(exc,'code',type(exc).__name__),'published':False}))
            continue
        print(json.dumps({'run_id': workspace.name, 'entries': len(manifest['entries']),
                          'source': manifest['roots']['source'], 'workspace': manifest['roots']['workspace'],
                          'database_scan': manifest['duckdb_scan'], 'published': not args.dry_run}))
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
