import pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))


@pytest.fixture(autouse=True)
def offline_feedback_delivery(monkeypatch):
    from cohort_lab import instructor_feedback
    def offline(*args):raise ConnectionError('offline test fixture')
    monkeypatch.setattr(instructor_feedback,'_post',offline)
    monkeypatch.setattr(instructor_feedback,'_client',lambda:{'client_id':'00000000-0000-4000-8000-000000000001','secret':'f'*43})


@pytest.fixture(autouse=True)
def offline_phase_coverage(monkeypatch):
    # Packet/ledger tests exercise the designed continuation phases internally.
    # Real subprocesses retain the release's startup-only policy.
    from unc_sol_bridge import config
    monkeypatch.setattr(config, "RELEASE_PHASES", frozenset({"startup", "pilot", "full"}))
