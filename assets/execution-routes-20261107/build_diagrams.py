"""Actual Archify editorial renders for integration into the main lab deck."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PIN = 'ff9c9d727ce298d16b91ba698aa99a0b6b1d2c51'
ORIGIN = 'https://github.com/longxiutian/customer-economics-lab.git'
p = argparse.ArgumentParser()
p.add_argument('--repo', type=Path, required=True)
p.add_argument('--node', required=True)
p.add_argument('--render', action='store_true')
a = p.parse_args()
folder = HERE / 'diagrams'
folder.mkdir(parents=True, exist_ok=True)
legend = {k: {'label':v} for k,v in {'frontend':'Interface', 'backend':'Computation', 'database':'Saved work', 'cloud':'Models', 'security':'Access', 'messagebus':'Routing'}.items()}

def n(key,label,detail,x,y,kind='backend',width=220,height=80,source='docs/execution-paths.md',lines=(7,16)):
    return {'id':key,'type':kind,'label':label,'sublabel':detail,'pos':[x,y],'size':[width,height],
            'sources':[{'path':source,'line':lines[0],'end_line':lines[1]}]}

def e(left,right,label): return {'from':left,'to':right,'label':label}

def save(name,title,nodes,edges,notes):
    candidate={'schema_version':1,'diagram_type':'architecture','meta':{'title':title,'locale':'en','output':f'diagrams/{name}.html',
        'visual_preset':'editorial','animation':'none','quality_profile':'showcase','legend':{'entries':legend},
        'repository':{'url':ORIGIN,'revision':PIN,'link_mode':'local-only'}},'components':nodes,'connections':edges,
        'cards':[{'dot':'cyan','title':'How to read this diagram','items':notes}]}
    (folder/f'{name}.json').write_text(json.dumps(candidate,indent=2)+'\n',encoding='utf-8')

save('personal','Personal coding agent: the lab runs in your workspace',[
    n('learner','Your questions','Ask, judge, next step',30,30,'frontend'),
    n('agent','Your coding agent','Codex / Claude / VS Code',365,30,'frontend',240),
    n('provider','Your model access','Plan or API account',720,30,'cloud'),
    n('files','Released lab files','8 CSVs + skills + assets',30,225,'database'),
    n('compute','Workspace execution','SQL, CPU fits, report',365,225,'backend',240),
    n('outputs','Your saved outputs','Report + personal debrief',720,225,'database',source='docs/personal-debrief.md',lines=(1,18)),
],[e('learner','agent','Ask'),e('agent','provider','Model calls'),e('agent','compute','Run'),e('files','compute','Inputs'),e('compute','outputs','Save')],[
    'The selected coding agent coordinates the tools. A local or cloud workspace executes the released code.',
    'VS Code requires an enabled agent and model access; the editor alone does not run the lab.',
    'Your own judgments and the executed evidence feed both the management report and a personal learning debrief.'
])

save('university-mcp','University-funded MCP: proposed scenario, TBD',[
    n('client','Student coding agent','Free-client suitability TBD',365,30,'frontend',240,source='docs/execution-paths.md',lines=(18,32)),
    n('native','Client model access','Own plan / client limits',720,30,'cloud',source='docs/execution-paths.md',lines=(27,32)),
    n('workspace','Your lab workspace','Code + data + outputs',30,225,'database',source='docs/execution-paths.md',lines=(20,25)),
    n('mcp','UNC MCP gateway','Sign-in + quotas: TBD',365,225,'security',240,source='docs/execution-paths.md',lines=(18,32)),
    n('funded','UNC-funded model','University usage receipts',720,225,'cloud',source='docs/execution-paths.md',lines=(20,25)),
],[e('client','native','Native calls'),e('client','workspace','Execute'),e('client','mcp','Tool call'),e('mcp','funded','Funded calls')],[
    'This is a scenario for investigation with UNC IT, not a released connection or funding commitment.',
    'MCP supplies tools and services. It does not automatically pay for or replace the coding client\'s native model.',
    'Native-client usage and university model usage remain separate streams in the same personal debrief.'
])

save('bluechip','BlueChip and Longleaf: shared service, personal lab',[
    n('browser','Your browser','UNC BlueChip sign-in',30,30,'frontend',source='docs/serving-architecture.md',lines=(9,16)),
    n('broker','Lab coordinator','Owns jobs + progress',365,30,'security',240,source='docs/serving-architecture.md',lines=(13,22)),
    n('cpu','CPU analysis worker','DuckDB, fits, charts, PDF',720,30,'backend',source='docs/serving-architecture.md',lines=(18,22)),
    n('gpu','Longleaf / Nemotron','Explains the evidence',365,225,'cloud',240,source='docs/serving-architecture.md',lines=(24,29)),
    n('work','Your saved workspace','Choices, results, report',720,225,'database',source='docs/serving-architecture.md',lines=(18,29)),
],[e('browser','broker','Lab tools'),e('broker','cpu','Run step'),e('cpu','gpu','Evidence'),e('gpu','cpu','Interpretation'),e('cpu','work','Save')],[
    'BlueChip provides the student interface and sign-in. Its interface model is distinct from Nemotron.',
    'CPU software computes the analysis; Nemotron interprets the returned evidence. Saved work is outside GPU memory.',
    'One-GPU rehearsal verified. Classroom provisioning and another student\'s complete sign-in test remain to be completed.'
])

save('four-gpus','Four independent Nemotron servers behind one router',[
    n('questions','Student requests','One shared entry point',30,130,'frontend',210,100,'docs/serving-architecture.md',(13,16)),
    n('router','Inference router','Queue, health, usage',365,110,'messagebus',240,140,'docs/serving-architecture.md',(31,53)),
    *[n('gpu'+str(i+1),'GPU '+str(i+1)+' / Nemotron','Same complete model',795,15+90*i,'cloud',220,64,'docs/serving-architecture.md',(31,36)) for i in range(4)],
],[e('questions','router','Queue'),*[e('router','gpu'+str(i+1),'Route '+str(i+1)) for i in range(4)]],[
    'Classroom design: four complete, independent model servers, each on one matching 96 GB GPU; not a model partitioned over four cards.',
    'The router admits requests fairly, skips unhealthy or expired replicas and records actual attempts and usage.',
    'GPU capacity scales interpretations; CPU fits and PDF compilation require separate capacity. Four live replicas are not claimed.'
])

save('workspaces','A shared release feeds separate student workspaces',[
    *[n('student'+str(i),'Student '+chr(65+i),'Authenticated login',30,25+135*i,'frontend',200,80,'docs/serving-architecture.md',(9,16)) for i in range(3)],
    *[n('workspace'+str(i),'Workspace '+chr(65+i),'Choices, fits, report',365,25+135*i,'database',240,80,'docs/serving-architecture.md',(13,29)) for i in range(3)],
    n('release','Shared source release','8 CSVs + skills + code',795,160,'backend',240,100,'docs/serving-architecture.md',(18,22)),
],[*[e('student'+str(i),'workspace'+str(i),'Own run') for i in range(3)],*[e('release','workspace'+str(i),'Read only') for i in range(3)]],[
    'The login-bound broker enforces ownership; a name typed into a prompt cannot select another student\'s workspace.',
    'The source release is read-only and reusable. Each run writes its own choices, checkpoints, model outputs and reports.',
    'The next GPU can change without resetting a student\'s work. Student identities shown here are illustrative.'
])

save('debrief','Every route ends with a personal learning debrief',[
    n('records','Your lab record','Questions + judgments',30,30,'database',source='docs/personal-debrief.md',lines=(23,55)),
    n('packet','Evidence snapshot','Outputs + usage coverage',365,30,'backend',240,source='docs/personal-debrief.md',lines=(57,117)),
    n('agent','Agent reviews evidence','Current agent / Opus',720,30,'cloud',source='docs/personal-debrief.md',lines=(9,21)),
    n('student','Same student','Local file / private link',30,225,'frontend',source='docs/personal-debrief.md',lines=(117,123)),
    n('debrief','Personal debrief','Studio North + AI prompts',365,225,'database',240,source='docs/personal-debrief.md',lines=(1,18)),
    n('check','Validate and review','Claims + source evidence',720,225,'security',source='docs/personal-debrief.md',lines=(97,123)),
],[e('records','packet','Freeze'),e('packet','agent','Evidence'),e('agent','check','Draft'),e('check','debrief','Review'),e('debrief','student','Deliver')],[
    'The requirement lives in the GitHub skills, so personal, university-funded and hosted routes share the same outcome.',
    'The current authorized agent can prepare feedback. Instructor-orchestrated Opus 5.5 high can refine the same evidence when available.',
    'Measured counters, recorded-text estimates and unavailable usage remain distinct. Central collection or delivery requires a configured authenticated path.'
])

if a.render:
    receipts=[]
    for name in ('bluechip','debrief','four-gpus','personal','university-mcp','workspaces'):
        candidate=folder/f'{name}.json'
        prior=folder/(name+'.receipt.json')
        receipt=json.loads(prior.read_text(encoding='utf-8')) if prior.exists() else {}
        if (receipt.get('ok') and candidate.with_suffix('.html').exists()
                and receipt.get('specification',{}).get('sha256')==hashlib.sha256(candidate.read_bytes()).hexdigest()): continue
        html=candidate.with_suffix('.html')
        cmd=[a.node,str(a.repo/'vendor/archify/bin/archify.mjs'),'finalize','architecture',str(candidate),str(html),
             '--repo-root',str(a.repo),'--quality','showcase','--json']
        if html.exists():
            versions=list(folder.glob(candidate.stem+'-review-*'))
            cmd += ['--out-dir',str(folder/(candidate.stem+'-review-'+str(len(versions)+1)))]
        run=subprocess.run(cmd,cwd=HERE,capture_output=True,text=True,encoding='utf-8')
        (folder/(candidate.stem+'.receipt.json')).write_text(run.stdout or '{}',encoding='utf-8')
        if run.returncode:
            print(candidate.stem,run.stdout[-5000:],run.stderr[-1000:]);raise SystemExit(run.returncode)
        info=json.loads(run.stdout)
        receipts.append({'name':candidate.stem,'ok':info.get('ok'),'status':info.get('status')})
        print(json.dumps(receipts[-1]),flush=True)
    cmd=[a.node,str(HERE/'export_slide_diagrams.mjs'),*[str(x) for x in sorted(folder.glob('*.html'))]]
    env={**os.environ,'COHORT_PLAYWRIGHT_MODULE':str(a.repo/'tools/node_modules/playwright')}
    subprocess.run(cmd,cwd=HERE,env=env,check=True)
