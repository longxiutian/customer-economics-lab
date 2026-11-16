"""Regression: a learner's multi-paragraph verdict must compile intact."""
import os
from pathlib import Path
import shutil

import pytest
from pypdf import PdfReader
from cohort_lab import report


def test_takeaway_preserves_paragraphs_and_escaped_text(tmp_path):
    if not (os.environ.get("COHORT_TEX_ENGINE") or any(shutil.which(x) for x in ["pdflatex", "tectonic"])):
        pytest.skip("Native TeX engine unavailable")
    root = Path(__file__).resolve().parents[1]
    for name in ["labreport.sty", "longxiu-research-brief.sty"]:
        shutil.copyfile(root / "templates" / name, tmp_path / name)
    verdict = "Retention improved by 10% & margin remained positive.\n\nKeep $50 of spend in channel_A while testing incrementality."
    source = tmp_path / "verdict.tex"
    source.write_text(
        r"\documentclass{article}\usepackage{labreport}\begin{document}" + "\n"
        + r"\Takeaway{" + report._tex(verdict) + "}\n"
        + r"\end{document}" + "\n", encoding="utf-8"
    )
    compiled = report._compile_native(source)
    assert compiled["overfull_boxes"] == 0
    pdf = PdfReader(source.with_suffix(".pdf"))
    assert len(pdf.pages) == 1
    text = " ".join((pdf.pages[0].extract_text() or "").split())
    for paragraph in verdict.split("\n\n"):
        assert paragraph in text
