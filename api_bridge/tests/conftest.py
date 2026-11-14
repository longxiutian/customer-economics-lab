import pytest


@pytest.fixture(autouse=True)
def offline_phase_coverage(monkeypatch):
    # Packet/ledger tests exercise the designed continuation phases internally.
    # Real subprocesses retain the release's startup-only policy.
    from unc_sol_bridge import config
    monkeypatch.setattr(config, "RELEASE_PHASES", frozenset({"startup", "pilot", "full"}))
