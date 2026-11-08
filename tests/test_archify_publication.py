import json
from pathlib import Path
import shutil
import subprocess

import pytest

from cohort_lab.diagrams import ROOT, _render_archify_html, _system_candidate


def test_native_render_copies_identical_html_into_durable_workspace(tmp_path, monkeypatch):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the real Archify renderer")
    scratch = tmp_path / "native-scratch"
    durable = tmp_path / "durable-workspace"
    scratch.mkdir(); durable.mkdir()
    monkeypatch.setenv("STUDIO_NORTH_JOB_RUNTIME", str(scratch))
    source = durable / "source-systems.json"
    source.write_text(json.dumps(_system_candidate([])), encoding="utf-8")
    renderer = ROOT / "vendor/archify/renderers/dataflow/render-dataflow.mjs"
    destination = durable / "source-systems.html"
    log = durable / "render.log"
    _render_archify_html(node, renderer, source, destination, log)
    first = destination.read_bytes()
    assert b"<html" in first.lower()
    assert not list(scratch.iterdir())
    _render_archify_html(node, renderer, source, destination, log)
    assert destination.read_bytes() == first
    assert sorted(p.name for p in durable.iterdir()) == ["render.log", "source-systems.html", "source-systems.json"]


def test_failed_render_preserves_existing_durable_artifact(tmp_path, monkeypatch):
    from cohort_lab import diagrams
    destination = tmp_path / "diagram.html"
    destination.write_bytes(b"previous verified HTML")
    def fail(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, "", "render rejected")
    monkeypatch.setattr(diagrams, "run_process", fail)
    with pytest.raises(RuntimeError, match="render rejected"):
        _render_archify_html("node", Path("renderer"), Path("source"), destination, tmp_path / "render.log")
    assert destination.read_bytes() == b"previous verified HTML"
