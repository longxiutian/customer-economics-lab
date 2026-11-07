"""Package an explicit, reviewed file list; never include private event stores."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from source_paths import lab_repository

ROOT = Path(__file__).resolve().parent
REPO = lab_repository()
REV = '3a109560dc064217bb662f4109e8265f7307497a'
BASE = 'aa32de4a33bd4c026ce38b30677ddb2b0ba8ca71'
(ROOT/'source-change.patch').write_bytes(subprocess.check_output(['git','diff','--binary',BASE,REV],cwd=REPO))
files = [
    '.gitattributes','README.md','index.html','slides.mjs','source_paths.py','build_diagrams.py',
    'finalize_diagrams.py','finish_debrief.py','render_debrief_pdf.py','package_sources.py',
    'source-change.patch','source-snapshot.bundle',
    'assets/reference-cover-0.jpeg','assets/reference-cover-1.png',
    'debrief-example/evidence-packet.json','debrief-example/opus-request.txt',
    'debrief-example/validated-response.json',
    'reviews/architecture-request.txt','reviews/architecture-response.json',
    'reviews/debrief-response.json','reviews/debrief-validation.json',
    'reviews/adjudication.md','reviews/qa.json',
    'output/Studio-North-Personal-Debrief-Example.pdf',
    'output/Studio-North-Personal-Debrief-Example.html',
]
for name in ['overview','four-gpus','workspaces','debrief']:
    files.extend(p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'diagrams').glob(name+'.*'))
                 if p.suffix in {'.json','.html'})
assert len(files) == len(set(files))
assert all('private-' not in name and not name.endswith('.sqlite') for name in files)
for name in files:
    if not (ROOT/name).is_file():
        raise FileNotFoundError(name)
hashes = {name: {'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),
                 'bytes': (ROOT/name).stat().st_size} for name in files}
manifest = {
    'schema_version': 1, 'date': '2026-11-07', 'title': 'Studio North serving architecture',
    'repository': 'https://github.com/longxiutian/customer-economics-lab',
    'implementation_commit': REV, 'implementation_base': BASE,
    'publication_status': 'Local commits and saved Spaces presentation; no Git push or service deployment',
    'presentation': {'page_id': 'page_4e018199c74c8191a445023b5b536679',
                     'artifact_ref': 'artifact_external_ca7b8f3a-bb9e-43ea-926e-de231205af62',
                     'state_version': 7, 'slides': 11},
    'archify_version': '3.2.0', 'python_for_pdf': sys.version,
    'reportlab_version': '4.4.9', 'pdf_font_requirement': 'Arial regular and bold',
    'snapshot_id': 'dc946ed7163c3c9b74afff49', 'fixture': 'Instructor rehearsal',
    'privacy': 'Explicit file list excludes private ledger, run/session mapping, live config and credentials.',
    'unrelated_dirty_file_excluded': 'docs/companion-slides.md',
    'files': hashes,
}
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8',newline='\n')
files.append('manifest.json')
archive = ROOT/'output/Studio-North-Architecture-Sources.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as out:
    for name in files:
        # Fixed timestamps make the archive reproducible for unchanged contents.
        info = zipfile.ZipInfo('studio-north-architecture/'+name,date_time=(2026,11,7,0,0,0))
        info.compress_type = zipfile.ZIP_DEFLATED
        out.writestr(info,(ROOT/name).read_bytes())
with zipfile.ZipFile(archive) as check:
    assert check.testzip() is None
    assert len(check.namelist()) == len(files)
destination = REPO/'assets/serving-architecture'
if destination.exists() and not (destination/'manifest.json').is_file():
    raise RuntimeError('Existing destination has no source-package manifest; inspect before updating.')
for name in files:
    target = destination/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/name,target)
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,
                  'files':len(files),'repository_sources':str(destination)}))
