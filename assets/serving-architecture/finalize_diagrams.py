import json
from pathlib import Path
import subprocess
import sys
from source_paths import lab_repository

HERE = Path(__file__).resolve().parent
WORK = HERE
REPO = lab_repository()
folder = HERE / 'diagrams'
(HERE / 'reviews').mkdir(exist_ok=True)
for name in sys.argv[1:]:
    args = ['node',str(REPO/'vendor/archify/bin/archify.mjs'),'finalize','architecture',str(folder/(name+'.json')),str(folder/(name+'.html')),'--repo-root',str(REPO),'--quality','showcase','--json']
    if (folder/(name+'.browser-check.json')).exists():
        count = 2
        while (folder/f'{name}-review-{count}').exists():
            count += 1
        args += ['--out-dir',str(folder/f'{name}-review-{count}')]
    p=subprocess.run(args,cwd=WORK,capture_output=True,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
    (HERE/'reviews'/f'archify-{name}-last.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8')
    try:
        v=json.loads(p.stdout)
        print(json.dumps({'name':name,'exit':p.returncode,'status':v.get('status'),'gates':v.get('gates'),'diagnostics':v.get('diagnostics'),'update':v.get('update'),'visual':v.get('visualReviewRecommendation')}),flush=True)
    except ValueError:
        print(json.dumps({'name':name,'exit':p.returncode,'output':(p.stdout+p.stderr)[-5000:]}),flush=True)
    if p.returncode:
        raise SystemExit(p.returncode)
