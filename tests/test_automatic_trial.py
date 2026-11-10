import json

import pytest

from cohort_lab import debrief
from scripts import run_automatic as automatic


@pytest.fixture
def trial(tmp_path, monkeypatch):
    calls = []
    control = {'ready': True, 'failure': None, 'inputs': {'dataset_version': '5.1', 'hashes': {'source': 'frozen'}}}
    monkeypatch.setattr(automatic, 'verify_frozen_inputs', lambda _: control['inputs'])
    monkeypatch.setattr(automatic, 'implementation_snapshot', lambda _: {'source.py': 'unchanged'})

    def stage(number, data, output, choices, **configuration):
        calls.append(number)
        assert choices == {}  # No invented learner recommendations or consent.
        assert configuration == {'seed': 20261116, 'steps': 3000, 'compile_pdf': True}
        if control['failure'] == number:
            raise RuntimeError('Representative computation failure')
        if number == 7:
            (output / 'report').mkdir()
            (output / 'report/customer-economics-report.pdf').write_bytes(b'fixture report')
        return {'ready': control['ready']} if number == 0 else {'stage': number}

    def validate(output, *, pdf):
        assert pdf and (output / 'report/customer-economics-report.pdf').is_file()
        calls.append('validate')
        return {'status': 'pass'}

    monkeypatch.setattr(automatic, 'execute_stage', stage)
    monkeypatch.setattr(automatic, 'validate', validate)
    return tmp_path / 'run', calls, control


def test_once_through_keeps_actual_prompt_and_produces_an_honest_debrief(trial):
    output, calls, _ = trial
    prompt = 'Please run the automatic trial and show me the result.'
    state = automatic.run(output, prompt=prompt, harness='Fixture agent')
    assert calls == [*range(8), 'validate']
    assert state['status'] == 'complete'
    assert state['messages'] == [{'text': prompt, 'kind': 'automatic-run-request'}]
    assert not (output / 'lesson_state.json').exists()
    assert not (output / 'lab_state.json').exists()
    assert not (output / 'learner_choices.json').exists()
    packet = debrief.snapshot(output)
    assert packet['metrics']['execution_mode'] == 'automatic-trial'
    assert packet['metrics']['checkpoint'] is None
    assert packet['metrics']['saved_judgments'] == 0
    assert packet['metrics']['lab_requests'] == 1
    assert packet['metrics']['full_session_inference_tokens'] is None
    assert any(e['kind'] == 'prompt_excerpt' and e['text'] == prompt for e in packet['evidence'])
    document = json.loads((output / 'debrief/latest.json').read_text())['debrief']
    from pathlib import Path
    assert 'automatic trial; no teaching checkpoints' in Path(document).read_text(encoding='utf-8')
    automatic.run(output, prompt=None, harness='Fixture agent', resume=True)
    assert calls == [*range(8), 'validate', 'validate']


def test_failed_readiness_does_not_start_analysis(trial):
    output, calls, control = trial
    control['ready'] = False
    with pytest.raises(ValueError, match='Environment is not ready'):
        automatic.run(output, prompt='Run automatically', harness='Fixture agent')
    assert calls == [0]
    state = json.loads((output / 'automatic_run.json').read_text())
    assert state['status'] == 'failed' and state['completed_stages'] == []
    assert state['stages']['0']['ready'] is False


def test_resume_retries_failed_stage_without_repeating_successful_work(trial):
    output, calls, control = trial
    control['failure'] = 6
    with pytest.raises(RuntimeError, match='Representative computation failure'):
        automatic.run(output, prompt='Run automatically', harness='Fixture agent')
    saved = json.loads((output / 'automatic_run.json').read_text())
    assert saved['completed_stages'] == list(range(6))
    control['failure'] = None
    automatic.run(output, prompt=None, harness='Fixture agent', resume=True)
    assert calls == [*range(7), 6, 7, 'validate']


def test_resume_rejects_changed_inputs_without_running_another_stage(trial):
    output, calls, control = trial
    control['ready'] = False
    with pytest.raises(ValueError):
        automatic.run(output, prompt='Run automatically', harness='Fixture agent')
    control['inputs'] = {'dataset_version': '5.1', 'hashes': {'source': 'changed'}}
    with pytest.raises(ValueError, match='Inputs, source or configuration changed'):
        automatic.run(output, prompt=None, harness='Fixture agent', resume=True)
    assert calls == [0]


def test_new_run_never_overwrites_an_existing_workspace(trial):
    output, calls, _ = trial
    output.mkdir()
    marker = output / 'my-existing-work.txt'
    marker.write_text('keep this')
    with pytest.raises(ValueError, match='fresh empty output folder'):
        automatic.run(output, prompt='Run automatically', harness='Fixture agent')
    assert marker.read_text() == 'keep this' and calls == []


def test_interrupt_is_recorded_and_no_later_stage_runs(trial, monkeypatch):
    output, calls, _ = trial
    def interrupted(*args, **kwargs):
        calls.append(args[0])
        raise KeyboardInterrupt()
    monkeypatch.setattr(automatic, 'execute_stage', interrupted)
    with pytest.raises(KeyboardInterrupt):
        automatic.run(output, prompt='Run automatically', harness='Fixture agent')
    state = json.loads((output / 'automatic_run.json').read_text())
    assert state['status'] == 'interrupted' and state['completed_stages'] == []
    assert calls == [0]
