"""Copy the inspected module and hash its reproducible source assets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
NAMES=('bluechip','debrief','four-gpus','personal','university-mcp','workspaces')
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);a=p.parse_args()
target=a.repo.resolve()/'assets/execution-routes-20261107'
target.mkdir(parents=True,exist_ok=True)
paths=[HERE/name for name in ('README.md','build_diagrams.py','export_slide_diagrams.mjs','slides.mjs','package_sources.py','.gitattributes')]
paths += [HERE/'diagrams'/(name+ext) for name in NAMES for ext in ('.json','.html','.svg','.png','.receipt.json')]
paths += list((HERE/'renders').glob('*.png'))+list((HERE/'renders').glob('*.layout.json'))
paths += [HERE/'reviews/qa.json']
manifest={'source_revision':'ff9c9d727ce298d16b91ba698aa99a0b6b1d2c51','page_id':'page_4e018199c74c8191a445023b5b536679',
          'state_version':12,'slide_count':9,'diagram_renderer':'Archify 3.2.0 editorial; Playwright 1.62.1',
          'files':{},'diagram_checks':{}}
for source in paths:
    relative=source.relative_to(HERE)
    dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,dest)
    manifest['files'][relative.as_posix()]={'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'bytes':dest.stat().st_size}
for name in NAMES:
    receipt=json.loads((HERE/'diagrams'/(name+'.receipt.json')).read_text(encoding='utf-8'))
    candidate=HERE/'diagrams'/(name+'.json')
    digest=hashlib.sha256(candidate.read_bytes()).hexdigest()
    assert receipt['ok'] and receipt['specification']['sha256']==digest, name
    manifest['diagram_checks'][name]={'status':receipt['status'],'gates':receipt['gates'],'candidate_sha256':digest}
(target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'target':str(target),'files':len(paths),'diagrams':len(NAMES)}))
