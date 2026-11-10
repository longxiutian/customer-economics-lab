#!/usr/bin/env python3
"""Temporary once-through trial using the unchanged canonical analytical stages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cohort_lab.workflow import execute_stage, implementation_snapshot, verify_frozen_inputs, _write_json
from cohort_lab import debrief
from scripts.validate_artifacts import validate


def run(output: Path, *, prompt: str | None, harness: str, resume: bool = False,
        compile_pdf: bool = True, seed: int = 20261116, steps: int = 3000,
        hosted: bool = False, progress=None) -> dict:
    """Keep a truthful automatic-run receipt, never synthetic learner consent."""
    output = Path(output).resolve()
    if steps < 3000:
        raise ValueError('Preserve the released inference budget: steps must be at least 3000.')
    if not harness.strip():
        raise ValueError('Name the actual coding-agent harness.')
    inputs = verify_frozen_inputs(ROOT / 'data')
    implementation = implementation_snapshot(ROOT)
    configuration = {'seed': seed, 'steps': steps, 'compile_pdf': compile_pdf, 'harness': harness}
    if hosted:
        configuration['hosted'] = True
    receipt = output / 'automatic_run.json'
    if resume:
        if not receipt.is_file():
            raise ValueError('No automatic trial exists here; use a fresh output folder.')
        state = json.loads(receipt.read_text(encoding='utf-8'))
        if state.get('mode') != 'automatic-trial' or state['inputs'] != inputs or state['implementation'] != implementation or state['configuration'] != configuration:
            raise ValueError('Inputs, source or configuration changed; restore the saved edition or start a fresh output folder.')
        if prompt is not None and prompt != state['messages'][0]['text']:
            raise ValueError('Preserve the actual original starting prompt when resuming.')
        if state['status'] == 'complete':
            validate(output, pdf=compile_pdf)
            return state
    else:
        if output.exists() and any(output.iterdir()):
            raise ValueError('Use a fresh empty output folder; existing work is never overwritten.')
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('Save the actual student request in --prompt-file before starting.')
        state = {'schema_version': 1, 'mode': 'automatic-trial', 'status': 'running',
                 'inputs': inputs, 'implementation': implementation, 'configuration': configuration,
                 'messages': [{'text': prompt, 'kind': 'automatic-run-request'}],
                 'completed_stages': [], 'stages': {}, 'recommendation_author': 'analyst',
                 'student_checkpoint_consent': 'not requested in this explicit automatic trial'}
    _write_json(receipt, state)
    if not hosted:
        debrief.initialize(output, route='personal', harness=harness)
    try:
        for stage in range(8):
            if stage in state['completed_stages']:
                continue
            state.update(status='running', active_stage=stage)
            state.pop('error', None)
            _write_json(receipt, state)
            print(f'Running analytical stage {stage} of 7', flush=True)
            if progress:
                progress('automatic_stage_' + str(stage))
            result = execute_stage(stage, ROOT / 'data', output, {}, seed=seed, steps=steps, compile_pdf=compile_pdf)
            state['stages'][str(stage)] = result
            if stage == 0 and not result.get('ready'):
                raise ValueError('Environment is not ready; inspect stage 0 in automatic_run.json, repair setup, then resume.')
            state['completed_stages'].append(stage)
            _write_json(receipt, state)
        state['validation'] = validate(output, pdf=compile_pdf)
        state.update(status='complete', active_stage=None)
        _write_json(receipt, state)
        if hosted:
            state['debrief_review'] = 'A separate instructor review job uses the actual hosted telemetry; no guided participation is claimed.'
        else:
            state['personal_debrief'] = debrief.prepare(output)
            state['debrief_review'] = 'The current agent must personalize, validate and render the saved scaffold before delivery.'
        _write_json(receipt, state)
        return state
    except BaseException as error:
        state.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
                     error={'type': type(error).__name__, 'message': str(error)})
        _write_json(receipt, state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs/automatic-trial')
    parser.add_argument('--prompt-file', type=Path, help='UTF-8 file containing the actual student starting request.')
    parser.add_argument('--harness', required=True, help='Actual coding-agent name, e.g. Codex or Claude Code.')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--seed', type=int, default=20261116)
    parser.add_argument('--steps', type=int, default=3000)
    parser.add_argument('--no-pdf', action='store_true')
    args = parser.parse_args()
    try:
        prompt = args.prompt_file.read_text(encoding='utf-8') if args.prompt_file else None
        state = run(args.output, prompt=prompt, harness=args.harness, resume=args.resume,
                    compile_pdf=not args.no_pdf, seed=args.seed, steps=args.steps)
        print(json.dumps({'status': state['status'], 'receipt': str(args.output / 'automatic_run.json'),
                          'report': str(args.output / 'report/customer-economics-report.pdf') if not args.no_pdf else None,
                          'personal_debrief': state.get('personal_debrief'), 'debrief_review': state.get('debrief_review')}, indent=2))
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
