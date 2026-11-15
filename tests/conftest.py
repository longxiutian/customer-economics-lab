"""Offline tests never submit fixture feedback to the live instructor service."""
import pytest


@pytest.fixture(autouse=True)
def offline_feedback_delivery(monkeypatch):
    from cohort_lab import instructor_feedback
    def offline(*args):raise ConnectionError('offline test fixture')
    monkeypatch.setattr(instructor_feedback,'_post',offline)
    monkeypatch.setattr(instructor_feedback,'_client',lambda:{'client_id':'00000000-0000-4000-8000-000000000001','secret':'f'*43})
