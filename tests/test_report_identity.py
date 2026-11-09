from pathlib import Path
import shutil

from pypdf import PdfReader, PdfWriter
import pytest
from reportlab.pdfgen.canvas import Canvas

from cohort_lab.report_identity import (KEY, content_sha256, inspect_pdf, load_identity,
                                        stamp_pdf, validate_cover)
from scripts.report_ids import summarize
from scripts.verify_reproducibility import comparison_hash


def fixture_pdf(path, course="Managing Customer Data", value="Same analysis"):
    canvas = Canvas(str(path), invariant=True)
    for size in [(612, 792), (1190.551, 841.89)]:
        canvas.setPageSize(size)
        canvas.setFillColorRGB(.15, .2, .3)
        canvas.rect(0, 0, *size, fill=1, stroke=0)
        canvas.setFillColorRGB(1, 1, 1)
        for i, line in enumerate(["Kenan-Flagler Business School", course, "Mod II 2026", value]):
            canvas.drawString(50, 700 - i * 22, line)
        canvas.showPage()
    canvas.save()


def test_workspace_identity_survives_rebuild_and_is_distinct_between_runs(tmp_path):
    a = load_identity(tmp_path / "a", create=True)
    assert load_identity(tmp_path / "a", create=True) == a
    assert load_identity(tmp_path / "b", create=True)["report_id"] != a["report_id"]
    assert set(a) == {"version", "report_id", "scope"}
    (tmp_path / "a/report_identity.json").write_text('{}')
    with pytest.raises(ValueError, match="Invalid saved"):
        load_identity(tmp_path / "a", create=True)


def test_footer_is_invisible_extractable_on_every_page_and_idempotent(tmp_path):
    pdf = tmp_path / "report.pdf"
    fixture_pdf(pdf)
    original = pdf.read_bytes()
    identity = load_identity(tmp_path, create=True)
    result = stamp_pdf(pdf, identity["report_id"])
    assert result["text_render_mode"] == 3 and result["pages"] == 2
    assert pdf.read_bytes() != original
    first = pdf.read_bytes()
    assert stamp_pdf(pdf, identity["report_id"]) == result
    assert pdf.read_bytes() == first
    assert inspect_pdf(pdf)["report_id"] == identity["report_id"]
    assert validate_cover(pdf)["course_neutral"]
    # A fresh compile of the same workspace remains byte-reproducible.
    pdf.write_bytes(original)
    stamp_pdf(pdf, identity["report_id"])
    assert pdf.read_bytes() == first


def test_distinct_ids_preserve_pdf_content_and_duplicates_count_once(tmp_path):
    source = tmp_path / "source.pdf"
    fixture_pdf(source)
    a, b, copy = [tmp_path / name for name in ["a.pdf", "b.pdf", "copy.pdf"]]
    shutil.copyfile(source, a)
    shutil.copyfile(source, b)
    id_a, id_b = [load_identity(tmp_path / name, create=True)["report_id"] for name in ["a", "b"]]
    stamp_pdf(a, id_a)
    stamp_pdf(b, id_b)
    assert a.read_bytes() != b.read_bytes()
    assert content_sha256(source) == content_sha256(a) == content_sha256(b)
    assert comparison_hash(tmp_path, "a.pdf") != comparison_hash(tmp_path, "b.pdf")
    shutil.copyfile(a, copy)
    summary = summarize([a, b, copy, source])
    assert summary["distinct_report_runs"] == 2
    assert len(summary["duplicate_ids"][id_a]) == 2
    assert len(summary["unmarked_or_invalid"]) == 1
    changed = tmp_path / "changed.pdf"
    fixture_pdf(changed, value="Different analysis")
    stamp_pdf(changed, id_a)
    assert content_sha256(changed) != content_sha256(a)


def test_reproduction_comparison_excludes_only_the_run_id(tmp_path):
    folders = [tmp_path / "a", tmp_path / "b"]
    for folder in folders:
        (folder / "report").mkdir(parents=True)
        pdf = folder / "report/customer-economics-report.pdf"
        fixture_pdf(pdf)
        stamp_pdf(pdf, load_identity(folder, create=True)["report_id"])
    name = "report/customer-economics-report.pdf"
    assert comparison_hash(folders[0], name) != comparison_hash(folders[1], name)
    assert comparison_hash(folders[0], name, ignore_report_identity=True) == comparison_hash(folders[1], name, ignore_report_identity=True)
    fixture_pdf(folders[1] / name, value="Changed recommendation")
    stamp_pdf(folders[1] / name, load_identity(folders[1])["report_id"])
    assert comparison_hash(folders[0], name, ignore_report_identity=True) != comparison_hash(folders[1], name, ignore_report_identity=True)


def test_foreign_identity_and_metadata_only_spoof_are_rejected(tmp_path):
    path = tmp_path / "report.pdf"
    fixture_pdf(path)
    report_id = load_identity(tmp_path, create=True)["report_id"]
    writer = PdfWriter(clone_from=path)
    writer.add_metadata({KEY: report_id})
    with path.open("wb") as stream:
        writer.write(stream)
    with pytest.raises(ValueError, match="footer"):
        inspect_pdf(path)
    fixture_pdf(path)
    stamp_pdf(path, report_id)
    with pytest.raises(ValueError, match="another report run"):
        stamp_pdf(path, "SN-" + "0" * 32)


def test_real_tex_report_preserves_nested_page_tree_content_and_neutral_cover(tmp_path):
    source = Path(__file__).resolve().parents[1] / "examples/reference/report/customer-economics-report.pdf"
    validate_cover(source)
    target = tmp_path / "report.pdf"
    shutil.copyfile(source, target)
    before = content_sha256(target)
    result = stamp_pdf(target, load_identity(tmp_path, create=True)["report_id"])
    assert result["pages"] == len(PdfReader(source).pages)
    assert result["content_sha256"] == before
    validate_cover(target)


@pytest.mark.parametrize("course", ["MBA 743: Managing Customer Data", "KFM 740", "MQM 553Q", "MSM 740"])
def test_course_specific_cover_fails_even_when_report_is_watermarked(tmp_path, course):
    path = tmp_path / "report.pdf"
    fixture_pdf(path, course)
    stamp_pdf(path, load_identity(tmp_path, create=True)["report_id"])
    with pytest.raises(ValueError, match="Course-specific"):
        validate_cover(path)
