import json
from pathlib import Path
import sys
from source_paths import lab_repository

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(lab_repository()))
from hosting.student_debrief import render, validate_response

raw = json.loads((ROOT / 'reviews/debrief-response.json').read_text(encoding='utf-8'))
response = raw.get('structuredContent') or json.loads(next(x['text'] for x in raw['content'] if x['type'] == 'text'))
assert not raw.get('isError') and response['model'] == 'claude-opus-5-5' and not response['incomplete'] and response['stop_reason'] == 'end_turn'
text = response['text'].strip()
if text.startswith('```json') and text.endswith('```'):
    text = text[7:-3].strip()
debrief = json.loads(text)
snapshot = json.loads((ROOT / 'debrief-example/evidence-packet.json').read_text(encoding='utf-8'))
# Retain the provider's original response above. Apply the documented Codex
# correction: the hosted lab already performs its prescribed fresh statistical
# fit; only changing the model/fitting code requires the external harness.
debrief['studio_north_next_steps'][1]['text'] = (
    'Frame the pilot recommendation as an acquisition-only channel holdout. '
    'Compare LTV before acquisition cost with LTV after current iCAC for each candidate cell. '
    'Trying a different statistical model or changing the fitting code requires a local/cloud '
    'coding harness with the repository; the hosted lab runs its prescribed fresh fit.'
)
debrief['studio_north_next_steps'][1]['prompt'] = (
    'Help me design an acquisition-only channel holdout for the proposed pilot cells. '
    'Keep retention and revenue fitting separate. Lay out how I would report LTV before '
    'acquisition cost and LTV after current iCAC per cell. Distinguish analyses supported '
    'by this hosted lab from model or code changes that need the repository in a coding harness.'
)
debrief['studio_north_next_steps'][1]['evidence_ids'].append('snap:' + snapshot['snapshot_id'] + '/ev:8')
validate_response(snapshot, debrief)
out = ROOT / 'output'
out.mkdir(exist_ok=True)
(ROOT / 'debrief-example/validated-response.json').write_text(json.dumps(debrief, indent=2, ensure_ascii=False), encoding='utf-8')
provenance = {'model': response['model'], 'effort': 'high', 'usage': {k: response['usage'][k] for k in ('input_tokens','output_tokens','thinking_tokens','total_tokens')}, 'scope': 'Operator debrief generation, excluded from student usage', 'fixture': 'Instructor rehearsal; not an actual student assessment', 'validation': 'Evidence IDs and exact quotations validated; narrative checked by Codex against the snapshot', 'codex_edit': 'Clarified that the hosted lab performs its prescribed fresh fit; alternative models or fitting-code changes need a coding harness. Original Opus response retained separately.'}
render(snapshot, debrief, path=out/'Studio-North-Personal-Debrief-Example.html', provenance=provenance)
(ROOT / 'reviews/debrief-validation.json').write_text(json.dumps({'snapshot_id': snapshot['snapshot_id'], 'validated': True, **provenance}, indent=2), encoding='utf-8')
print(json.dumps({'validated': True, 'model': response['model'], 'output': str(out/'Studio-North-Personal-Debrief-Example.html')}))
