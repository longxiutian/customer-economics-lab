"""Export the exact MCP teaching frames for the gateway, without model calls."""
import ast
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'api_bridge/src'))
from unc_sol_bridge.config import BridgeConfig
from unc_sol_bridge.packets import TEACHER_CONTRACT,EXTRA_ARTIFACTS,compile_packet,load_lessons,source_fingerprint
from unc_sol_bridge.projects import PROJECT_CONTRACT, REVISION, CODE_SUFFIXES, PRIVATE_PARTS, registered_artifacts


def export():
    lessons=load_lessons(ROOT)
    tree=ast.parse((ROOT/'hosting/student_debrief.py').read_text(encoding='utf-8'))
    rubric=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(getattr(t,'id',None)=='RUBRIC' for t in n.targets))
    with tempfile.TemporaryDirectory() as temporary:
        base=Path(temporary);run=base/'run';run.mkdir()
        (run/'lesson_state.json').write_text(json.dumps({'completed_step':0,'results':{'0':{}}}),encoding='utf-8')
        config=BridgeConfig(base/'config.json',ROOT,ROOT/'data',run,base/'state','export','2026-11',0,'offline export',400000,'startup',10000,5000,source_fingerprint(ROOT),{'kind':'env','name':'NOT_USED'})
        packet=compile_packet(config,'open')
    target=ROOT/'api_bridge/admission'
    opening={'instructions':packet.instructions,'packet':packet.text,'input_bytes':packet.input_bytes}
    curriculum={'revision':'studio-north-guided/2','teacher':TEACHER_CONTRACT,'debrief':rubric,'lessons':[
        {'title':lesson.title,'objective':lesson.objective,'check':lesson.check,
         'artifacts':[p for p in lesson.files if p!='learner_choices.json']+list(EXTRA_ARTIFACTS.get(i,()))}
        for i,lesson in enumerate(lessons)]}
    project={'revision':REVISION,'contract':PROJECT_CONTRACT,'artifacts':registered_artifacts(lessons),
             'dashboard_suffixes':CODE_SUFFIXES,'private_parts':PRIVATE_PARTS,
             'learner_max_bytes':4096,'note_max_bytes':2048,'previous_max_bytes':1600}
    for name,value in (('opening.json',opening),('curriculum.json',curriculum),('project.json',project)):
        (target/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'checkpoints':len(lessons),'opening_bytes':packet.input_bytes}))


if __name__=='__main__':export()
