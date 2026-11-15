"""Instructor-only feedback export. Writes private JSON and prints counts, never replies or identities."""
import argparse
import json
import os
from pathlib import Path
import re
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
URL='https://studio-north-bluechip-lab.blondeflour1.chatgpt.site/api/feedback/v1/export'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def export(path,token):
    path=Path(path).resolve()
    if path.is_relative_to(ROOT) or path.exists():raise ValueError('Choose a new private file outside the public repository.')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    after=0;rows=[]
    for _ in range(100):
        request=urllib.request.Request(URL+'?limit=200&after='+str(after),headers={'Authorization':'Bearer '+token,'User-Agent':'StudioNorth-InstructorFeedback/1.0'})
        with opener.open(request,timeout=20) as response:
            raw=response.read(4*1024*1024+1)
            if len(raw)>4*1024*1024:raise ValueError('Export response exceeded its bound.')
            page=json.loads(raw)
        if page.get('ok') is not True or not isinstance(page.get('rows'),list):raise ValueError('Invalid private export response.')
        rows.extend(page['rows'])
        if not page['rows']:break
        cursor=page.get('next_cursor')
        if type(cursor) is not int or cursor<=after:raise ValueError('Invalid export cursor.')
        after=cursor
    else:raise ValueError('Export exceeded 20,000 rows; use a separately scoped export.')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    descriptor=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as stream:json.dump({'schema_version':1,'rows':rows},stream,ensure_ascii=False,indent=2)
    return {'saved_to':str(path),'rows':len(rows)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--token-env',default='STUDIO_NORTH_FEEDBACK_ADMIN_TOKEN')
    args=parser.parse_args()
    if not re.fullmatch('[A-Z][A-Z0-9_]{2,100}',args.token_env) or not os.environ.get(args.token_env):
        raise SystemExit('The instructor credential reference is unavailable. No student export was requested.')
    try:result=export(args.output,os.environ[args.token_env])
    except Exception as error:raise SystemExit('Private export did not complete ('+type(error).__name__+'). No reply text was printed.') from None
    print(json.dumps(result))
