// Reusable Artifact Session callbacks; no standalone deck or export on import.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const ROOT=path.dirname(fileURLToPath(import.meta.url));
const P={navy:'#13294B',blue:'#4B9CD3',ink:'#1F2B36',slate:'#627488',line:'#C7D8E6',concept:'#155B88',teal:'#126A5C',orange:'#914509',pale:'#E8F2F9'};
const SOURCE='Source: Studio North architecture contract and instructor rehearsal, 7 Nov 2026';
function tx(s,text,x,y,w,h,size=23,color=P.ink,bold=false,align='left'){
  const q=s.shapes.add({geometry:'textbox',name:text.slice(0,65),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  q.text=text;q.text.style={fontFamily:'Arial',fontSize:size,color,bold,alignment:align,wrap:'word',autoFit:'none',verticalAlignment:'middle',insets:{left:0,right:0,top:0,bottom:0}};return q;
}
function rect(s,x,y,w,h,fill,stroke='none',strokeWidth=0){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:stroke,width:strokeWidth}});}
function rule(s,x,y,w,color=P.line){return s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:0},fill:'none',line:{fill:color,width:1}});}
function base(p,title,lead,role='concept'){
  const s=p.slides.add({width:1280,height:720});s.background.fill='#FFFFFF';
  const ink=role==='evidence'?P.navy:role==='case'?P.teal:P.concept;
  rect(s,0,0,1280,7,role==='case'?'#269B87':role==='evidence'?P.slate:P.blue);
  tx(s,'STUDIO NORTH / SERVING ARCHITECTURE',64,35,860,25,11.5,P.slate,true);
  tx(s,role==='evidence'?'EVIDENCE & INTERPRETATION':role==='case'?'CASE APPLICATION':'CONCEPT',880,35,336,25,13,ink,true,'right');
  tx(s,title,64,86,1152,76,34,ink,true);tx(s,lead,76,165,1128,60,22,P.slate);
  tx(s,String(p.slides.items.length),1180,680,36,20,11,P.slate,false,'right');return s;
}
function note(s,text,sources=[]){s.speakerNotes.textFrame.setText(text+'\n\nSources\n'+sources.join('\n'));}
function band(s,text){rect(s,64,615,1152,55,P.pale);tx(s,text,80,619,1120,45,20,P.concept);}
function node(s,label,detail,x,y,w=220,h=88,color=P.concept){
  const q=rect(s,x,y,w,h,'#FFFFFF',color,1.8);
  tx(s,label,x+10,y+8,w-20,h*.42,22,color,true,'center');
  if(detail)tx(s,detail,x+10,y+h*.48,w-20,h*.43,18,P.ink,false,'center');return q;
}
function edge(s,a,b,{from='right',to='left',color=P.slate}={}){return s.shapes.connect(a,b,{fromSide:from,toSide:to,kind:'straight',line:{fill:color,width:2},tail:{type:'triangle',width:'med',length:'med'}});}
async function spec(name){return JSON.parse(await fs.readFile(ROOT+'/diagrams/'+name+'.json','utf8'));}
function provenance(specification){return ['Archify 3.2.0 source: '+specification.meta.output.replace('.html','.json'),'Repository: '+specification.meta.repository.url,'Pinned local source commit: '+specification.meta.repository.revision,'Contract: docs/serving-architecture.md; per-node source ranges retained in the Archify candidate.'];}

export async function cover({presentation:p}){
  if(p.slides.items.length===1){
    const blank=p.slides.getItem(0);
    if(blank.shapes.items.length||blank.images.items.length)throw Error('Create a new empty presentation for reproduction');
    p.slides.delete(0);
  }
  if(p.slides.items.length)throw Error('Create a new empty presentation for reproduction');
  const s=p.slides.add({width:1280,height:720});s.background.fill=P.navy;
  s.images.add({path:ROOT+'/assets/reference-cover-0.jpeg',position:{left:0,top:0,width:1280,height:480},fit:'cover'});
  tx(s,'MANAGING CUSTOMER DATA  /  MOD II 2026',64,509,1152,30,20,P.blue,true);
  tx(s,'Inside the Studio North AI Lab',64,558,1152,63,42,'#FFFFFF',true);
  tx(s,'BlueChip, Longleaf and your personal workspace',64,638,1152,40,25,'#FFFFFF');
  note(s,'Architecture supplement using the established course cover assets. The teaching concepts describe both the verified rehearsal and the proposed classroom extension.',['Current course reference: customer-economics-lab.pdf, cover; assets retained in this source package.']);
  return {slides:p.slides.items.length};
}

export async function opening({presentation:p}){
  if(p.slides.items.length!==1)throw Error('Expected the existing cover only');
  const cover=p.slides.getItem(0);
  cover.images.add({path:ROOT+'/assets/reference-cover-1.png',position:{left:25,top:30,width:275,height:85},fit:'contain'});
  let s=base(p,'How to read the slide colors','Color identifies the teaching task.');
  const key=[['Concept','Definitions and frameworks explain the ideas.',P.concept,'#E8F2F9'],['Case application','Studio North connects the architecture to your lab.',P.teal,'#E4F3EE'],['Evidence and interpretation','Observed records support a conclusion.',P.navy,'#EEF1F5'],['Group exercise and review','Apply an idea, then compare your reasoning.',P.orange,'#FCE5C9']];
  for(let i=0;i<key.length;i++){const [label,body,color,fill]=key[i];const y=244+i*90;rect(s,76,y,245,66,fill);tx(s,label,91,y+5,215,56,20,color,true);tx(s,body,355,y,845,66,23);}
  note(s,'Course color key, matching the current MBA/MSM teaching composition. This supplement uses concept, case and evidence slides.','Current course reference: customer-economics-lab.pdf, slides 1–3, MBA 743 course folder, November 2026.'.split('\n'));
  s=base(p,'Three principles behind the lab','How can many students use shared AI without sharing their work?');
  const rows=[['Separation of roles','The AI interprets evidence. Executable analysis produces the tables, model estimates and report.'],['Isolation','Your login maps to your saved choices, checkpoint, fitted outputs and report.'],['Traceability','Recorded requests and model receipts connect your questions to results and personal feedback.']];
  for(let i=0;i<3;i++){const y=240+i*120;tx(s,rows[i][0],76,y,235,96,23,P.navy,true);tx(s,rows[i][1],331,y,873,96,23);if(i<2)rule(s,76,y+110,1128);}
  note(s,'These are concepts, not a setup checklist. The student uses the browser; computing and persistence are managed centrally.','docs/serving-architecture.md, lines 9–29 and 61–109'.split('\n'));
  return {slides:p.slides.items.length};
}

export async function systems({presentation:p}){
  if(p.slides.items.length!==3)throw Error('Expected cover, key and concepts');
  let d=await spec('overview');let s=base(p,'One browser link connects three kinds of work','BlueChip presents the lesson; CPU software computes; Nemotron explains.','case');
  const a=node(s,'Your browser','No installation',64,265,170,84),b=node(s,'BlueChip','Sign-in + chat',318,265,180,84),c=node(s,'Lab coordinator','Jobs + progress',584,265,210,84),cpu=node(s,'Analysis host','DuckDB + CPU fits',935,265,260,84);
  edge(s,a,b);edge(s,b,c);edge(s,c,cpu);tx(s,'Sign in',237,259,78,35,16,P.slate,false,'center');tx(s,'Lab API',501,259,80,35,16,P.slate,false,'center');tx(s,'Run a step',801,259,128,35,16,P.slate,false,'center');
  const gpu=node(s,'Longleaf / Nemotron','Interpret this evidence',584,475,250,90,P.teal),files=node(s,'Your workspace','Tables, fits, charts, PDF',935,475,260,90,P.teal);
  edge(s,cpu,files,{from:'bottom',to:'top'});tx(s,'Save outputs',1072,383,130,36,17,P.slate,false,'center');
  edge(s,cpu,gpu,{from:'bottom',to:'right'});edge(s,gpu,cpu,{from:'top',to:'left'});tx(s,'Evidence',844,442,100,32,16,P.slate).fill='#FFFFFF';tx(s,'Explanation',760,389,135,32,16,P.slate).fill='#FFFFFF';
  band(s,'Your decisions and outputs are saved outside the language model.');note(s,'Verified role split from the one-GPU rehearsal. The analysis host was the instructor’s Windows CPU worker; cloud D1 stores broker state and R2 stores uploaded artifact copies. The interface model configured in BlueChip is distinct from Nemotron. Native editable adaptation of the Archify overview; use the companion HTML for full source cards.',provenance(d));
  d=await spec('four-gpus');s=base(p,'Four GPUs serve four copies of Nemotron','Classroom design: one router chooses an available, healthy replica.','case');
  const req=node(s,'Student questions','One shared entry point',76,355,230,100);const router=node(s,'Inference router','Fair queue + health checks',425,325,270,160);
  edge(s,req,router);tx(s,'Queue',327,362,78,32,18,P.slate,false,'center');
  for(let i=0;i<4;i++){const q=node(s,'GPU '+(i+1)+'  /  Nemotron','Independent model server',880,240+i*88,310,68,P.teal);edge(s,router,q);}
  band(s,'GPUs scale AI responses. CPU fits and PDF builds still need their own capacity.');
  note(s,'Proposed classroom topology; four GPUs are not claimed live or load-tested. Each full model runs on a matching 96 GB RTX PRO 6000 Blackwell card. TP=PP=DP=1 per independent process. The router limits each student’s active work and skips unhealthy/expired/mismatched replicas. Eight engine sequences per GPU was a configured ceiling, not a throughput guarantee. Do not automatically retry a possibly dispatched request. Students do not choose or connect to individual GPU ports.',[...provenance(d),'https://docs.vllm.ai/en/latest/serving/parallelism_scaling/','https://docs.vllm.ai/en/latest/serving/data_parallel_deployment/']);
  d=await spec('workspaces');s=base(p,'Shared infrastructure, separate student workspaces','Your login controls which saved analysis the lab can read or update.','case');
  const ws=[];for(let i=0;i<3;i++){const y=252+i*114;const who=node(s,'Student '+String.fromCharCode(65+i),'BlueChip login',76,y,205,78);const w=node(s,'Workspace '+String.fromCharCode(65+i),'Choices + model + report',442,y,310,78,P.teal);ws.push(w);edge(s,who,w);tx(s,'Bound by login',288,y-2,146,35,17,P.slate,false,'center');}
  const release=node(s,'Shared source release','8 CSVs + skills + assets',949,350,265,106);for(const w of ws)edge(s,release,w,{from:'left',to:'right'});tx(s,'Read only',780,361,125,35,18,P.slate,false,'center');
  band(s,'A different GPU can answer the next question without resetting your workspace.');note(s,'Student A/B/C are illustrative identities, not real students. Login ownership is enforced by the broker, not by the model’s text. Inputs and code are frozen and read-only; each run writes its own state, receipts, fit and report. A multi-host CPU deployment needs shared durable storage or stable workspace ownership. The current prototype’s SQLite router is local IPC only.',provenance(d));
  return {slides:p.slides.items.length};
}

export async function feedback({presentation:p}){
  if(p.slides.items.length!==6)throw Error('Expected six slides');
  let s=base(p,'What the lab can record for you','Your login links each recorded question to its result.');
  const labels=[['Received request','Question + checkpoint'],['Model attempt','Replica + model version'],['Returned result','Text + usage + outcome']];const nodes=labels.map((v,i)=>node(s,v[0],v[1],76+i*400,260,320,105));edge(s,nodes[0],nodes[1]);edge(s,nodes[1],nodes[2]);
  tx(s,'Prompts and choices',76,415,315,45,24,P.navy,true);tx(s,'The message received by the lab API and the judgments you save.',76,466,315,103,23);
  tx(s,'Measured model use',476,415,315,45,24,P.navy,true);tx(s,'Input/output tokens, queue time and elapsed response time.',476,466,315,103,23);
  tx(s,'Evidence of completion',876,415,315,45,24,P.navy,true);tx(s,'Checkpoint, output files, success, failure or uncertain outcome.',876,466,315,103,23);
  band(s,'Nemotron usage is measured. Native BlueChip chat usage needs a separate connection.');note(s,'Implemented prototype coverage: worker receipts and physical Nemotron attempts. Tool-forwarded messages may be reformulated and do not establish a complete verbatim native-chat transcript. Status-only/native-interface turns are outside this worker ledger. The visible BlueChip context-occupancy breakdown is not cumulative usage. Input tokens include system instructions, evidence and template tokens; missing counts remain unknown. Cache/reasoning subsets are not added to total again. No TTFT is reported for nonstreaming calls.','docs/serving-architecture.md, lines 61–81; hosting/telemetry.py; hosting/inference_router.py'.split('\n'));
  let d=await spec('debrief');s=base(p,'Codex turns your lab evidence into a personal debrief','Opus 5.5 at high effort drafts the feedback; Codex checks its evidence.');
  const events=node(s,'Your lab records','Questions, choices, outputs',76,270,285,90),packet=node(s,'Codex: prepare','Freeze + redact your evidence',493,270,285,90),opus=node(s,'Opus 5.5 / high','Draft useful feedback',910,270,285,90,P.teal);
  const student=node(s,'Private delivery','To the same student',76,475,285,90,P.teal),report=node(s,'Personal debrief','Studio North + AI next steps',493,475,285,90),check=node(s,'Codex: verify','Check claims + citations',910,475,285,90);
  edge(s,events,packet);edge(s,packet,opus);edge(s,opus,check,{from:'bottom',to:'top'});edge(s,check,report,{from:'left',to:'right'});edge(s,report,student,{from:'left',to:'right'});
  band(s,'Each recommendation points to your evidence and ends with a prompt you can try.');note(s,'This is the intended personal-debrief flow, implemented as a local prototype with one instructor fixture. Identity-to-recipient lookup stays in a separate protected delivery store; it is not sent to Opus. The full Archify companion adds that registry explicitly. Codex validates evidence IDs and exact quotes, then checks the reasoning before delivery. A failed narrative falls back to measured metrics. Native BlueChip usage is not invented; tokens do not grade learning. Delivery channel and real student bindings remain to be selected/verified.',provenance(d));
  s=base(p,'The debrief ends with useful next questions','Example from the instructor rehearsal; these are not student performance measures.','evidence');
  const metrics=[['25','lab requests'],['20','Nemotron responses'],['127,200','reported Nemotron tokens']];for(let i=0;i<3;i++){tx(s,metrics[i][0],76+i*400,242,320,72,48,P.navy,true);tx(s,metrics[i][1],76+i*400,317,320,42,21,P.slate);}
  rule(s,76,387,1128);
  tx(s,'Studio North',76,420,520,40,25,P.navy,true);tx(s,'“Compare channel-by-need cells at the same cohort age. Show the spread of customer contribution within each cell.”',76,477,520,110,24);
  tx(s,'AI practice',686,420,518,40,25,P.navy,true);tx(s,'“Tag each claim as computed evidence, a saved judgment, or your interpretation. Show me the source.”',686,477,518,110,24);
  note(s,'Measured instructor rehearsal only: 25 lab API requests; five saved judgments; 19 checkpoints (0–18); one fresh fit; 20 completed Nemotron responses; 115,639 input + 11,561 output = 127,200 tokens. These are provider-reported workload counts, including system instructions/evidence. Native BlueChip GPT usage is unknown. The illustrative prompt examples condense the evidence-linked Opus recommendations. The debrief correctly identified the instructor acceptance-test judgments. Example snapshot: dc946ed7163c3c9b74afff49. Opus debrief generation separately used 6,598 tokens at high effort.', ['debrief-example/evidence-packet.json (redacted instructor fixture)','reviews/debrief-validation.json','output/Studio-North-Personal-Debrief-Example.html']);
  s=base(p,'What is verified, and what comes next','The four-GPU classroom service is the next deployment.','evidence');
  const status=[['Verified rehearsal','One GPU, one CPU worker, separate runs and the full report generated from fresh fits.'],['Built and tested locally','Fair routing, usage records, isolated evidence snapshots and an Opus-generated example debrief.'],['Classroom activation','Four live replicas, enough CPU capacity, a real student sign-in check and private debrief delivery.']];
  for(let i=0;i<3;i++){const y=240+i*120;tx(s,status[i][0],76,y,240,96,23,P.navy,true);tx(s,status[i][1],340,y,864,96,23);if(i<2)rule(s,76,y+110,1128);}
  note(s,'The source modules are not a deployed four-GPU service. The prior fixed-window rehearsal remains frozen. No new or extended GPU allocation is claimed. Real-class throughput depends on both CPU and GPU queues. Delivery selection remains pending, and this prototype has sent no student messages. Preserve these status distinctions when reusing the slides.', ['docs/bluechip-classroom.md','docs/serving-architecture.md','tests/test_lab_telemetry.py','reviews/adjudication.md']);
  s=base(p,'Sources and reproducibility','The diagrams, code and feedback rubric have reproducible source files.','evidence');
  const refs=[['1  Studio North implementation','Versioned architecture contract; workspace, router, telemetry and debrief code. Local source snapshot: 3a10956.'],['2  Serving evidence','Longleaf one-GPU rehearsal receipts and vLLM documentation on independent replicas and MoE data parallelism.'],['3  Diagram and debrief sources','Archify 3.2.0 candidates and standalone HTML; editable slide callbacks; frozen example evidence and Opus receipts.']];
  for(let i=0;i<3;i++){const y=238+i*122;tx(s,refs[i][0],76,y,1128,37,24,P.navy,true);tx(s,refs[i][1],76,y+43,1128,65,22);}
  note(s,'Primary/public sources and local provenance. Sources are descriptions of the deployed rehearsal and the proposed extension, not a claim that four GPUs are currently running.', ['https://github.com/longxiutian/customer-economics-lab','docs/serving-architecture.md at commit 3a109560dc064217bb662f4109e8265f7307497a (local commit; not published)','https://docs.vllm.ai/en/latest/serving/parallelism_scaling/','https://docs.vllm.ai/en/latest/serving/data_parallel_deployment/','https://github.com/tt-a1i/archify/tree/25cf37080fc8b1dbe758a4efc3935b55f3327083','Operator serving configuration and checkpoint identity receipts, November 7, 2026','Slide source: studio_north_architecture_20261107/slides.mjs']);
  return {slides:p.slides.items.length};
}
