// Integration subsection. All diagrams are genuine Archify exports, not slide redraws.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const ROOT=path.dirname(fileURLToPath(import.meta.url));
const P={navy:'#13294B',blue:'#4B9CD3',ink:'#1F2B36',slate:'#627488',line:'#C7D8E6',concept:'#155B88',teal:'#126A5C',pale:'#E8F2F9'};
const PIN='ff9c9d727ce298d16b91ba698aa99a0b6b1d2c51';
function tx(s,text,x,y,w,h,size=23,color=P.ink,bold=false,align='left'){
  const q=s.shapes.add({geometry:'textbox',name:text.slice(0,65),position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  q.text=text;q.text.style={fontFamily:'Arial',fontSize:size,color,bold,alignment:align,wrap:'word',autoFit:'none',verticalAlignment:'middle',insets:{left:0,right:0,top:0,bottom:0}};return q;
}
function rect(s,x,y,w,h,fill){return s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill,line:{fill:'none',width:0}});}
function rule(s,x,y,w,color=P.line){return s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:0},fill:'none',line:{fill:color,width:1}});}
function base(p,title,lead,role='concept'){
  const s=p.slides.add({width:1280,height:720});s.background.fill='#FFFFFF';
  const ink=role==='evidence'?P.navy:role==='case'?P.teal:P.concept;
  rect(s,0,0,1280,7,role==='case'?'#269B87':P.blue);
  tx(s,'STUDIO NORTH / WAYS TO RUN THE LAB',64,35,850,25,11.5,P.slate,true);
  tx(s,role==='evidence'?'EVIDENCE & INTERPRETATION':role==='case'?'CASE APPLICATION':'CONCEPT',880,35,336,25,13,ink,true,'right');
  tx(s,title,64,86,1152,76,34,ink,true);tx(s,lead,76,166,1128,52,22,P.slate);
  tx(s,String(p.slides.items.length),1180,680,36,20,11,P.slate,false,'right');return s;
}
function note(s,text,sources=[]){s.speakerNotes.textFrame.setText(text+'\n\nSources / reproduction\n'+sources.join('\n'));}
async function diagram(s,name,{top=225,height=438}={}){
  s.images.add({path:path.join(ROOT,'diagrams',name+'.png'),position:{left:56,top,width:1168,height},fit:'contain'});
  const d=JSON.parse(await fs.readFile(path.join(ROOT,'diagrams',name+'.json'),'utf8'));
  return ['Actual Archify 3.2.0 editorial render: diagrams/'+name+'.png; JSON, HTML and native SVG retained.',
    'Sources verified at '+PIN+' in '+d.meta.repository.url,
    ...d.cards.flatMap(c=>c.items)];
}

function divider(p){
  const s=p.slides.add({width:1280,height:720});s.background.fill=P.navy;
  rect(s,76,264,1128,3,P.blue);
  tx(s,'Three ways to run\nStudio North',76,305,1128,154,49,'#FFFFFF',true);
  note(s,'Subtopic divider for insertion into the main lab deck after the separate business-motivation subsection. This is an integration module, so it has no repeated course cover or color key. Preserve the main deck\'s final FAQ sequence.', ['build-longxiu-academic-slides: current navy subtopic divider standard.']);
  return s;
}

export async function start({presentation:p}){
  // Only the independent staging deck: never call start on the main course deck.
  p.slides.delete(p.slides.items.map(s=>s.id));divider(p);
  return {slides:p.slides.items.length};
}

export async function personal({presentation:p,integrating=false}){
  if(!integrating&&p.slides.items.length!==1)throw Error('Expected subsection divider');
  let s=base(p,'Three routes support the same learning workflow','You ask questions, inspect the evidence and advance one step at a time.');
  const rows=[
    ['1','Your coding agent','Codex, Claude Code or VS Code with an agent','Your local/cloud workspace; your model account.',P.concept],
    ['2','UNC-funded access — TBD','A coding agent connected to a university model service','Funding, connection and free-client suitability to be tested.',P.concept],
    ['3','BlueChip + Longleaf','A browser interface with instructor-managed computing','UNC sign-in; available during the announced service window.',P.teal],
  ];
  for(let i=0;i<rows.length;i++){
    const [num,label,detail,implication,color]=rows[i], y=250+i*128;
    tx(s,num,76,y,60,70,43,color,true);tx(s,label,160,y,1044,37,27,color,true);
    tx(s,detail,160,y+42,1044,35,22);tx(s,implication,160,y+79,1044,32,20,P.slate);
    if(i<2)rule(s,160,y+119,1044);
  }
  note(s,'Same eight datasets and 19 guided checkpoints, same analytical contract and two final artifacts. Students write no analytical code themselves; an enabled harness or the hosted service executes the code. The university route is a proposal, not an announced entitlement. BlueChip classroom activation is separate from the expired Nov7 pilot.', ['docs/execution-paths.md','README.md student prompts','https://code.visualstudio.com/docs/agent-customization/language-models']);
  s=base(p,'Your coding agent runs the lab in your workspace','Open the released lab folder, paste the student prompt and follow the checkpoints.','case');
  const sources=await diagram(s,'personal');
  note(s,'Codex, Claude Code and VS Code with an enabled agent are alternatives within this route. Their supported plan/provider settings determine model access. The agent reads SKILL.md and the student-teacher skill, runs the pinned analysis in its accessible local/cloud environment, and shows real intermediate evidence. VS Code is the editor; an actual agent and provider are needed. Personal usage logging starts with the lesson; the final report and learning debrief are saved to the learner\'s workspace. Never turn a plan-usage percentage into an invented token count.', [...sources,'docs/execution-paths.md:7–16','docs/personal-debrief.md','https://code.claude.com/docs/en/costs','https://code.visualstudio.com/docs/agent-customization/language-models']);
  s=base(p,'UNC-funded model access is a scenario to test','TBD: a university model service could supply additional reasoning through MCP.','case');
  const unc=await diagram(s,'university-mcp');
  note(s,'MCP means Model Context Protocol: a way for an agent to use external tools and services. An authenticated UNC tool could call a university-funded model and return evidence/usage receipts. It does not automatically replace or pay for the client\'s own conversational model. A free coding-client plan remains subject to its own limits; complete-lab suitability must be tested. Funding, identity, quotas and classroom support are pending UNC IT decisions. Native-client and gateway usage are recorded separately. The analysis still needs a working local/cloud execution workspace.', [...unc,'docs/execution-paths.md:18–32','https://learn.chatgpt.com/docs/extend/mcp?surface=cli','https://learn.chatgpt.com/docs/pricing']);
  return {slides:p.slides.items.length};
}

export async function hosted({presentation:p,integrating=false}){
  if(!integrating&&p.slides.items.length!==4)throw Error('Expected four slides');
  let s=base(p,'BlueChip connects your browser to the lab','CPU software computes; Nemotron explains.\nOne-GPU rehearsal complete; classroom activation pending.','case');
  let refs=await diagram(s,'bluechip');
  note(s,'A student signs in to UNC BlueChip and opens the instructor-supplied Studio North agent. No local installation, GPU endpoint selection or tunnel client is needed. BlueChip\'s interface model and Nemotron are separate. A broker binds the platform login to the private run; CPU software performs actual SQL, statistical fits, charts and TeX/PDF compilation. One-GPU instructor rehearsal produced the correct report with fresh fits. Its Nov7 window has expired. A new classroom service window, real-student access and whole-class capacity require verification. The main Day page must publish the active connection when confirmed, not promise the expired pilot.', [...refs,'docs/bluechip-classroom.md','docs/serving-architecture.md:9–29']);
  s=base(p,'One entry point can serve a class through four GPUs','Classroom design: the router assigns each question to an available copy of Nemotron.','case');
  refs=await diagram(s,'four-gpus',{top:222,height:446});
  note(s,'Four complete, independent model replicas, each on one matching96GB RTX PRO6000 Blackwell GPU, with TP=PP=DP=1 per process. A fair router limits active work per student, checks health and expiry, and measures each physical model attempt. Four GPUs increase simultaneous interpretation capacity; they do not make one answer four times faster or eliminate the separate CPU fitting/PDF queue. The service is a classroom design, not a claim that four GPUs are live. Students use one entry point and do not choose a GPU. A timeout after possible dispatch requires reconciliation rather than blind replay.', [...refs,'docs/serving-architecture.md:31–60','https://docs.vllm.ai/en/latest/serving/parallelism_scaling/','https://docs.vllm.ai/en/latest/serving/data_parallel_deployment/']);
  s=base(p,'Shared computing keeps each student’s work separate','Your login owns your saved choices, checkpoint, fitted results and report.','case');
  refs=await diagram(s,'workspaces',{top:220,height:448});
  note(s,'The diagram illustrates three learners, not actual student identities. The authenticated broker enforces ownership; a name inside a prompt cannot override it. Code/data are shared read-only; each workspace writes its own state and results. A later question can go to a different GPU without losing progress because persistent work is outside model memory. Local coding-agent users instead keep their own lab folder; this diagram describes the hosted login binding. A multi-host CPU design also needs shared durable storage or stable run ownership.', [...refs,'docs/serving-architecture.md:13–29,56–60']);
  return {slides:p.slides.items.length};
}

export async function finish({presentation:p,integrating=false}){
  if(!integrating&&p.slides.items.length!==7)throw Error('Expected seven slides');
  let s=base(p,'Your usage record distinguishes counts from estimates','The goal is to improve how you work with AI; token volume is not a learning score.','evidence');
  const rows=[
    ['Measured','Provider receipts or supported session counters.','Keep the agent, university service and Nemotron streams separate.'],
    ['Estimated','An explicitly labeled estimate of recorded text.','This excludes hidden reasoning, repeated context and missing tool traffic.'],
    ['Unknown','Full usage when the harness does not expose it.','A subscription percentage or context-window display is not a token total.']
  ];
  for(let i=0;i<3;i++){
    const y=250+i*128;tx(s,rows[i][0],76,y,245,58,28,P.navy,true);
    tx(s,rows[i][1],355,y,849,43,24);tx(s,rows[i][2],355,y+51,849,63,21,P.slate);
    if(i<2)rule(s,76,y+118,1128);
  }
  note(s,'The portable recorder uses actual session receipts when available, with provider-specific cache semantics and explicit cumulative baselines. Otherwise UTF8bytes/4, sensitivity2–6bytes/token, estimates only recorded visible text. This is not a statistical interval, full inference total, bill or weekly-plan fraction. Complete usage is never inferred from partial records. Hosted Nemotron receipts exclude native BlueChip inference unless a separate supported usage feed exists. Exact prompts captured depend on the route; forwarded tool requests are not necessarily verbatim native chat. Local logs remain in the student workspace by default; central collection is separate.', ['docs/personal-debrief.md:57–95','cohort_lab/debrief.py:63–199','https://code.claude.com/docs/en/costs','https://code.visualstudio.com/docs/configure/telemetry']);
  s=base(p,'Every route ends with a report and a personal debrief','Your questions and judgments guide next steps for Studio North and your AI practice.','case');
  const refs=await diagram(s,'debrief');
  note(s,'Two distinct artifacts: the executive report addresses the business decision; the personal debrief reflects on the learner\'s recorded analysis and AI interaction. It includes evidence-linked observations, two Studio North next steps and two AI-practice next steps with prompts. The current authorized agent can draft and review it; the instructor can orchestrate Opus5.5high against the same redacted evidence packet when available. No student must buy separate Opus access. The final checkpoint produces a transparent scaffold; the agent must review/personalize it before delivery. Hosted delivery must bind to the authenticated student; local delivery is a private workspace file.\n\nExample Studio North prompt: Compare within-cell dispersion and across-cell differences at matched cohort ages; does the segmentation earn its complexity?\nExample AI-practice prompt: Trace one recommendation to executed SQL, a saved table or report exhibit; distinguish my judgment from model interpretation.', [...refs,'SKILL.md personal-debrief contract','skills/student-teacher/SKILL.md','docs/personal-debrief.md:97–123']);
  return {slides:p.slides.items.length};
}

export async function appendSection({presentation:p}){
  // Non-destructive integration: append, then the course owner reorders these IDs
  // before the existing FAQ divider and renumbers the main deck's footers.
  const before=new Set(p.slides.items.map(s=>s.id));
  divider(p);
  await personal({presentation:p,integrating:true});
  await hosted({presentation:p,integrating:true});
  await finish({presentation:p,integrating:true});
  return {addedSlideIds:p.slides.items.filter(s=>!before.has(s.id)).map(s=>s.id)};
}
