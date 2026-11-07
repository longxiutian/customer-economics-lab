"""Author reproducible Archify candidates for the architecture teaching module."""
import json
from pathlib import Path
import subprocess
from source_paths import lab_repository

HERE = Path(__file__).resolve().parent
WORK = HERE
REPO = lab_repository()
marker = HERE / 'diagram-root.txt'
folder = HERE / 'diagrams'
folder.mkdir(parents=True, exist_ok=True)
marker.write_text(str(folder), encoding='utf-8')
revision = subprocess.check_output(['git','rev-parse','3a109560dc064217bb662f4109e8265f7307497a'], cwd=REPO, text=True).strip()
origin = 'https://github.com/longxiutian/customer-economics-lab.git'

def source(start, end):
    return [{'path':'docs/serving-architecture.md','line':start,'end_line':end,'label':'Versioned architecture contract'}]

def n(key, label, detail, x, y, width=185, height=76, kind='backend', lines=(9,29)):
    return {'id':key,'type':kind,'label':label,'sublabel':detail,'pos':[x,y],'size':[width,height],'sources':source(*lines)}

def edge(a,b,label,**kw):
    return {'from':a,'to':b,'label':label,**kw}

def save(name, title, nodes, edges, cards):
    out = folder / (name + '.html')
    data={'schema_version':1,'diagram_type':'architecture','meta':{'title':title,'locale':'en','output':out.relative_to(WORK).as_posix(),'visual_preset':'blueprint','quality_profile':'showcase','repository':{'url':origin,'revision':revision,'link_mode':'local-only'}},'components':nodes,'connections':edges,'cards':cards}
    (folder/(name+'.json')).write_text(json.dumps(data,indent=2),encoding='utf-8')

save('overview','Studio North: browser, analysis and interpretation',[
    n('student','Student browser','No local installation',40,40,150,76,'frontend',(9,11)),
    n('bluechip','BlueChip','Sign-in + chat interface',280,40,160,76,'frontend',(9,16)),
    n('broker','Lab broker','Owns jobs + progress',540,40,190,76,'security',(13,16)),
    n('cpu','CPU analysis worker','SQL, models, charts, PDF',870,40,220,76,'backend',(18,22)),
    n('nemotron','Longleaf / Nemotron','Explains computed evidence',540,260,190,76,'cloud',(24,29)),
    n('files','Student workspace','Choices + tables + report',870,260,220,76,'database',(18,29)),
], [edge('student','bluechip','Sign in'),edge('bluechip','broker','Lab API'),edge('broker','cpu','Queued job'),edge('cpu','files','Save outputs'),edge('cpu','nemotron','Evidence'),edge('nemotron','cpu','Explanation')], [
    {'dot':'cyan','title':'One browser link','items':['BlueChip handles sign-in and the lesson interface. The interface model is distinct from Nemotron.']},
    {'dot':'emerald','title':'Computed evidence','items':['Eight frozen CSVs feed DuckDB and CPU statistical fits. Python, Archify and TeX create the report.']},
    {'dot':'amber','title':'Verified rehearsal','items':['One GPU and one serial CPU worker were verified. Four-GPU classroom serving is a separate proposed deployment.']},
])
save('four-gpus','Four independent Nemotron replicas: classroom design',[
    n('requests','Student requests','Authenticated run IDs',40,205,180,90,'frontend',(13,16)),
    n('router','Fair inference router','Queue + health + usage',360,205,220,90,'messagebus',(38,53)),
    *[n('gpu'+str(i+1),'GPU '+str(i+1)+' / Nemotron','Same pinned model',810,35+125*i,220,76,'cloud',(33,36)) for i in range(4)]
], [edge('requests','router','Queue'),*[edge('router','gpu'+str(i+1),'Route '+str(i+1)) for i in range(4)]], [
    {'dot':'cyan','title':'Independent copies','items':['Each GPU runs a complete model server. The router selects a healthy replica with available capacity.']},
    {'dot':'emerald','title':'Fair admission','items':['One active request per student, bounded queues and persistent attempt records. Unknown dispatch outcomes are held for reconciliation.']},
    {'dot':'amber','title':'Capacity has two parts','items':['More GPUs serve more interpretations concurrently. Parallel CPU fits and report builds still need their own capacity and durable storage.']},
])
save('workspaces','Shared source release, separate student workspaces',[
    n('a','Student A','BlueChip login A',40,40,155,76,'frontend',(9,16)),
    n('b','Student B','BlueChip login B',40,190,155,76,'frontend',(9,16)),
    n('c','Student C','BlueChip login C',40,340,155,76,'frontend',(9,16)),
    n('wa','Workspace A','A: choices, fits, PDF',365,40,225,76,'database',(18,22)),
    n('wb','Workspace B','B: choices, fits, PDF',365,190,225,76,'database',(18,22)),
    n('wc','Workspace C','C: choices, fits, PDF',365,340,225,76,'database',(18,22)),
    n('release','Shared release','8 CSVs + skills + code',835,190,225,76,'backend',(18,22)),
], [edge('a','wa','Broker binds A'),edge('b','wb','Broker binds B'),edge('c','wc','Broker binds C'),edge('release','wa','Read only'),edge('release','wb','Read only'),edge('release','wc','Read only')], [
    {'dot':'cyan','title':'Identity is authoritative','items':['The broker binds the signed-in student to a private run. A model-generated name cannot select another workspace.']},
    {'dot':'emerald','title':'Progress persists','items':['Choices, intermediate outputs and reports survive between questions. A new chat resumes the same run.']},
    {'dot':'amber','title':'GPU assignment can change','items':['Workspaces are outside GPU memory. Switching the serving replica does not reset the student’s analysis.']},
])
save('debrief','A personal debrief grounded in one student’s lab evidence',[
    n('events','Recorded lab activity','Messages + tokens + results',40,40,220,76,'database',(63,81)),
    n('snapshot','Codex: freeze evidence','One student, redacted packet',405,40,245,76,'backend',(85,89)),
    n('opus','Opus 5.5 / high','Evidence-linked feedback',820,40,225,76,'cloud',(91,102)),
    n('review','Codex: validate','Check claims + citations',820,265,225,76,'security',(97,102)),
    n('report','Personal debrief','Studio North + AI next steps',405,265,245,76,'backend',(97,107)),
    n('student','Same student','Private delivery',40,265,220,76,'frontend',(104,109)),
    n('identity','Recipient registry','Separate protected mapping',405,455,245,76,'security',(104,109)),
], [edge('events','snapshot','Freeze'),edge('snapshot','opus','Evidence'),edge('opus','review','Draft'),edge('review','report','Validated'),edge('report','student','Deliver once'),edge('identity','report','Recipient')], [
    {'dot':'cyan','title':'Observed activity','items':['The router measures Nemotron usage. Native BlueChip chat tokens and unforwarded turns are outside current coverage.']},
    {'dot':'emerald','title':'Useful next steps','items':['Feedback cites actual questions, saved judgments and outputs. It proposes both analytical extensions and better ways to work with AI.']},
    {'dot':'amber','title':'Prototype status','items':['An instructor example has been generated. Classroom delivery and a real-student authentication check are still to be configured and verified.']},
])
print(json.dumps({'folder':str(folder),'revision':revision,'candidates':['overview','four-gpus','workspaces','debrief']}))
