"""Explicit automatic test adapter, separate from the learner-gated lesson."""
from __future__ import annotations

import json
from pathlib import Path

from .workflow import WorkflowError, implementation_snapshot, verify_frozen_inputs

MODE = 'automatic-test'
START_MESSAGE = 'Run the Studio North automatic test and generate my report and personal debrief.'


class AutomaticTest:
    def __init__(self, data_dir, output_dir, *, progress=None):
        self.data_dir = Path(data_dir)
        self.output = Path(output_dir)
        self.path = self.output / 'automatic_run.json'
        self.progress = progress

    def start(self, message):
        if self.path.exists():
            return self.status()
        from scripts.run_automatic import run
        run(self.output, prompt=message, harness='BlueChip + Longleaf Nemotron',
            hosted=True, progress=self.progress)
        return self.status()

    def status(self):
        from .lab_close import summary
        state = json.loads(self.path.read_text(encoding='utf-8'))
        if state['implementation'] != implementation_snapshot() or state['inputs'] != verify_frozen_inputs(self.data_dir):
            raise WorkflowError('The automatic test release changed; preserve the original workspace for operator review.')
        if state['status'] != 'complete' or state['completed_stages'] != list(range(8)):
            raise WorkflowError('The automatic test did not finish; operator recovery is required. No work was repeated.')
        return {'mode': MODE, 'step': 18, 'total_steps': 8, 'advanced': False,
                'title': 'Automatic test report', 'choices': {},
                'guided_participation': False, 'recommendation_author': 'analyst',
                'completed_stages': state['completed_stages'],
                'objective': 'Review the computed Studio North report and its evidence.',
                'check': 'This automatic test does not establish completion of the guided lesson or independent student judgments.',
                'closing':summary(self.output),
                'message': 'Report ready. Say end lab or end simulation when finished; then answer the instructor-feedback question before the usage report.',
                'result': {'files': [{'path': str(self.path)}]}}

    def handle_message(self, message):
        # Actual questions are logged by HostedLesson; no computation restarts.
        from .lab_close import handle,summary
        handle(self.output,message)
        result=self.status();closing=summary(self.output)
        if closing['state']=='awaiting_feedback':result['message']=closing['question']
        return result

    def set_choice(self, key, value):
        raise WorkflowError('This automatic test has an analyst recommendation. It cannot be converted into guided participation by saving a choice.')
