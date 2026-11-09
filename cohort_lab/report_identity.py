"""An invisible, local report-run identifier; no registration or personal data."""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import uuid

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                           NameObject, TextStringObject)

IDENTITY_FILE = "report_identity.json"
KEY = "/StudioNorthReportID"
FONT = "/StudioNorthInvisibleFont"
PATTERN = re.compile(r"SN-[0-9A-F]{32}\Z")


def load_identity(output: Path, *, create: bool = False) -> dict:
    """Keep one random ID per output workspace, including report rebuilds."""
    path = Path(output) / IDENTITY_FILE
    if create and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        candidate = {"version": 1, "report_id": "SN-" + uuid.uuid4().hex.upper(),
                     "scope": "report-run"}
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(candidate, indent=2, sort_keys=True) + "\n")
        except FileExistsError:
            pass
    value = json.loads(path.read_text(encoding="utf-8"))
    if (set(value) != {"version", "report_id", "scope"} or value["version"] != 1
            or value["scope"] != "report-run"
            or not isinstance(value["report_id"], str) or not PATTERN.fullmatch(value["report_id"])):
        raise ValueError("Invalid saved report identity; preserve the original workspace identity")
    return value


def _streams(page) -> list:
    contents = page.get("/Contents")
    if contents is None:
        return []
    value = contents.get_object()
    return list(value) if isinstance(value, ArrayObject) else [contents]


def _footer(page, report_id: str) -> bytes:
    box = page.get("/CropBox", page["/MediaBox"]).get_object()
    x, y = float(box[0]) + 36, float(box[1]) + 12
    # Rendering mode 3 neither fills nor strokes text: invisible on any background.
    return (f"q\nBT\n{FONT} 6 Tf\n3 Tr\n1 0 0 1 {x:g} {y:g} Tm\n"
            f"(Studio North report ID: {report_id}) Tj\nET\nQ\n").encode("ascii")


def inspect_pdf(path: Path) -> dict:
    """Require the same invisible marker on every page and in PDF metadata."""
    reader = PdfReader(path)
    report_id = (reader.metadata or {}).get(KEY)
    if not isinstance(report_id, str) or not PATTERN.fullmatch(report_id) or not reader.pages:
        raise ValueError("PDF has no valid Studio North report ID")
    for page in reader.pages:
        marked = [s.get_object() for s in _streams(page) if KEY in s.get_object()]
        if (len(marked) != 1 or marked[0][KEY] != report_id
                or marked[0].get_data() != _footer(page, report_id)):
            raise ValueError("Missing, changed or inconsistent invisible report footer")
        font = page["/Resources"]["/Font"].get(FONT)
        if font is None or font.get_object().get("/BaseFont") != "/Helvetica":
            raise ValueError("Missing invisible report footer font")
        if report_id not in (page.extract_text() or ""):
            raise ValueError("Report ID must remain readable by PDF text extraction")
    return {"report_id": report_id, "pages": len(reader.pages),
            "scope": "report-run", "text_render_mode": 3}


def content_sha256(path: Path) -> str:
    """Compare PDF content with only this module's ID layer/metadata removed."""
    reader = PdfReader(path)
    if (reader.metadata or {}).get(KEY) is not None:
        inspect_pdf(path)
    for page in reader.pages:
        page[NameObject("/Contents")] = ArrayObject(
            [s for s in _streams(page) if KEY not in s.get_object()])
        resources = page.get("/Resources")
        if resources is not None:
            resources = DictionaryObject(resources.get_object())
            fonts = resources.get("/Font")
            if fonts is not None:
                fonts = DictionaryObject(fonts.get_object())
                fonts.pop(FONT, None)
                if not fonts:
                    resources.pop("/Font", None)
                else:
                    resources[NameObject("/Font")] = fonts
            page[NameObject("/Resources")] = resources
        # PdfReader's flattened PageObject may be a copy of the page-tree object.
        if page.indirect_reference is not None:
            page.indirect_reference.get_object().update(page)
    info = reader.trailer.get("/Info")
    if info is not None:
        info.get_object().pop(KEY, None)
    # Clone only the remaining referenced objects, excluding removed marker objects.
    writer = PdfWriter(clone_from=reader)
    buffer = BytesIO()
    writer.write(buffer)
    # The first clone flattens nested TeX page trees but can retain their now
    # unreachable parent objects. A second clone prunes those consistently.
    canonical = BytesIO()
    PdfWriter(clone_from=PdfReader(BytesIO(buffer.getvalue()))).write(canonical)
    return hashlib.sha256(canonical.getvalue()).hexdigest()


def stamp_pdf(path: Path, report_id: str) -> dict:
    """Add an extractable invisible footer without changing the rendered report."""
    if not PATTERN.fullmatch(report_id):
        raise ValueError("Invalid report ID")
    reader = PdfReader(path)
    existing = (reader.metadata or {}).get(KEY)
    if existing is not None:
        result = inspect_pdf(path)
        if existing != report_id:
            raise ValueError("PDF already belongs to another report run")
        return {**result, "content_sha256": content_sha256(path)}
    before = content_sha256(path)
    writer = PdfWriter(clone_from=reader)
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
        NameObject("/Encoding"): NameObject("/WinAnsiEncoding")}))
    for page in writer.pages:
        resources = DictionaryObject(page.get("/Resources", DictionaryObject()).get_object())
        fonts = DictionaryObject(resources.get("/Font", DictionaryObject()).get_object())
        if FONT in fonts or any(KEY in s.get_object() for s in _streams(page)):
            raise ValueError("Conflicting report footer resources")
        fonts[NameObject(FONT)] = font
        resources[NameObject("/Font")] = fonts
        page[NameObject("/Resources")] = resources
        marker = DecodedStreamObject()
        marker.set_data(_footer(page, report_id))
        marker[NameObject(KEY)] = TextStringObject(report_id)
        page[NameObject("/Contents")] = ArrayObject([*_streams(page), writer._add_object(marker)])
    writer.add_metadata({KEY: report_id})
    buffer = BytesIO()
    writer.write(buffer)
    temporary = Path(path).with_name(Path(path).name + ".identity.tmp")
    try:
        temporary.write_bytes(buffer.getvalue())
        result = inspect_pdf(temporary)
        after = content_sha256(temporary)
        if before != after:
            raise ValueError("Invisible report footer changed other PDF content")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return {**result, "content_sha256": after}


def validate_cover(path: Path) -> dict:
    """Reject a stale course-specific cover before any generated report is delivered."""
    text = " ".join((PdfReader(path).pages[0].extract_text() or "").split())
    if re.search(r"\b(?:MBA|MSM|MQM|KFM)\s*[-:]?\s*\d{3}\w?\b", text, re.I):
        raise ValueError("Course-specific cover label; regenerate from the current neutral templates")
    for line in ("Kenan-Flagler Business School", "Managing Customer Data", "Mod II 2026"):
        if line not in text:
            raise ValueError(f"Missing neutral report cover credit: {line}")
    return {"status": "passed", "course_neutral": True}
