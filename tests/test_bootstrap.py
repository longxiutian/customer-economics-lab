"""Student downloads must pin one guided revision and reject legacy launchers."""
import hashlib
import io
import json
import subprocess
import urllib.error
import zipfile

import pytest

from scripts import bootstrap


def archive_bytes(*, omit=(), extra=()):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name in sorted((bootstrap.GUIDED_FILES - set(omit)) | set(extra)):
            archive.writestr('lab-source/' + name, 'fixture')
    return stream.getvalue()


class Response(io.BytesIO):
    def __init__(self, body, url):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url


@pytest.mark.parametrize('missing', ['skills/student-teacher/SKILL.md', 'student.py', 'cohort_lab/student.py'])
def test_legacy_archive_is_rejected_before_extracting(tmp_path, missing):
    archive = tmp_path / 'old.zip'
    archive.write_bytes(archive_bytes(omit=[missing]))
    destination = tmp_path / 'student'
    with pytest.raises(ValueError, match='guided student edition'):
        bootstrap.install_archive(archive, destination)
    assert not destination.exists()


@pytest.mark.parametrize('launcher', sorted(bootstrap.INSTRUCTOR_LAUNCHERS))
def test_instructor_launcher_is_not_installed(tmp_path, launcher):
    archive = tmp_path / 'mixed.zip'
    archive.write_bytes(archive_bytes(extra=[launcher]))
    destination = tmp_path / 'student'
    with pytest.raises(ValueError, match='batch/replay launcher'):
        bootstrap.install_archive(archive, destination)
    assert not destination.exists()


@pytest.mark.parametrize('ref', ['main', 'b' * 40])
def test_download_pins_source_and_records_archive_without_processes(tmp_path, monkeypatch, ref):
    commit = 'b' * 40
    body = archive_bytes()
    calls = []

    def open_url(request, *, timeout):
        calls.append(request.full_url)
        assert timeout in (30, 90)
        if request.full_url.endswith('/commits/main'):
            return Response(json.dumps({'sha': commit}).encode(), request.full_url)
        assert request.full_url == bootstrap.archive_url(commit)
        return Response(body, 'https://codeload.github.com/' + bootstrap.PUBLIC_REPOSITORY + '/zip/' + commit)

    def forbidden(*args, **kwargs):
        raise AssertionError('Student source retrieval must not launch Git, a terminal, or another process')

    monkeypatch.setattr(bootstrap.urllib.request, 'urlopen', open_url)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    path = bootstrap.download_lab(tmp_path / 'student', ref)
    assert len(calls) == (2 if ref == 'main' else 1)
    saved = json.loads((path / 'source_checkout.json').read_text())
    assert saved['commit'] == commit
    assert saved['requested_ref'] == ref
    assert saved['source_url'] == bootstrap.archive_url(commit)
    assert saved['archive_sha256'] == hashlib.sha256(body).hexdigest()
    assert saved['entrypoint'] == 'student.py'
    assert (path / 'skills/student-teacher/SKILL.md').is_file()
    assert not (path / 'outputs').exists()


def test_default_lookup_failure_never_falls_back_to_an_old_release(tmp_path, monkeypatch):
    calls = []

    def unavailable(request, *, timeout):
        calls.append(request.full_url)
        raise urllib.error.URLError('offline fixture')

    monkeypatch.setattr(bootstrap.urllib.request, 'urlopen', unavailable)
    with pytest.raises(urllib.error.URLError):
        bootstrap.download_lab(tmp_path / 'student')
    assert calls == ['https://api.github.com/repos/' + bootstrap.PUBLIC_REPOSITORY + '/commits/main']
    assert not (tmp_path / 'student').exists()


def test_invalid_revision_response_never_downloads_an_archive(tmp_path, monkeypatch):
    calls = []

    def invalid(request, *, timeout):
        calls.append(request.full_url)
        return Response(b'{"sha":"main"}', request.full_url)

    monkeypatch.setattr(bootstrap.urllib.request, 'urlopen', invalid)
    with pytest.raises(ValueError, match='full commit SHA'):
        bootstrap.download_lab(tmp_path / 'student')
    assert len(calls) == 1
    assert not (tmp_path / 'student').exists()
