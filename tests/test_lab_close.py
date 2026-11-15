import json
from pathlib import Path

import pytest

from cohort_lab.lab_close import QUESTION, handle, read, summary, require_ended, binding
from cohort_lab.debrief import initialize, prepare, record, snapshot


def workspace(tmp_path):
    (tmp_path/'lesson_state.json').write_text(json.dumps({'completed_step':3,'messages':[
        {'text':'Why preaggregate before joining?', 'purpose':'lab','happened_at':1}]}))
    initialize(tmp_path,route='university_mcp',harness='Codex')
    return tmp_path


@pytest.mark.parametrize('trigger',['end lab','END SIMULATION!'])
def test_end_waits_for_feedback_and_allows_partial_debrief(tmp_path,trigger):
    root=workspace(tmp_path)
    with pytest.raises(ValueError,match='locked'):prepare(root)
    assert not (root/'debrief').exists()
    assert not handle(root,'What happens when I end lab?')
    assert handle(root,trigger)
    assert summary(root)['question']==QUESTION
    assert not summary(root)['usage_report_allowed']
    before=read(root)
    for message in ('next step','',trigger):
        assert handle(root,message)
        assert read(root)==before
    with pytest.raises(ValueError,match='locked'):prepare(root)
    assert handle(root,'skip feedback')
    assert require_ended(root)['usage_report_allowed']
    assert Path(prepare(root)['debrief']).is_file()


def test_feedback_stays_local_and_later_activity_is_excluded(tmp_path):
    root=workspace(tmp_path)
    record(root,{'event_id':'first','kind':'text','role':'assistant','text':'Aggregate each source to customer-month first.'})
    handle(root,'end lab')
    handle(root,'Please spend longer explaining joins, Professor Tian.')
    assert read(root)['feedback']['reply'].startswith('Please spend longer')
    frozen=snapshot(root)
    assert 'Please spend longer' not in json.dumps(frozen)
    assert frozen['closing']['feedback']['local_original']
    record(root,{'event_id':'late','kind':'text','role':'assistant','text':'This arrived after the cutoff.'})
    assert snapshot(root)==frozen
    receipt=binding(root)
    assert handle(root,'end simulation') and binding(root)==receipt
    handle(root,'continue lab')
    with pytest.raises(ValueError):prepare(root)
    handle(root,'end simulation');handle(root,'no feedback')
    assert snapshot(root)['snapshot_id']!=frozen['snapshot_id']


def test_changed_artifacts_require_a_new_close(tmp_path):
    root=workspace(tmp_path)
    handle(root,'end lab');handle(root,'no')
    (root/'learner_choices.json').write_text('{"final_verdict":"Changed"}')
    with pytest.raises(ValueError,match='changed after ending'):prepare(root)
