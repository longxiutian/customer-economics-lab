#!/usr/bin/env python3
"""Download a pinned guided-student archive without Git or external processes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

PUBLIC_REPOSITORY = "longxiutian/customer-economics-lab"
DEFAULT_REF = "main"
MAX_DOWNLOAD = 128 * 1024 * 1024
MAX_EXTRACTED = 512 * 1024 * 1024
GUIDED_FILES = {"SKILL.md", "skills/student-teacher/SKILL.md", "student.py",
                "cohort_lab/student.py", "lab.py", "pyproject.toml"}
INSTRUCTOR_LAUNCHERS = {"batch.py", "replay_report.py", "scripts/batch.py", "scripts/replay_report.py"}


def archive_url(ref: str) -> str:
    if not ref or any(character in ref for character in ("\\", "?", "#", "..")):
        raise ValueError("Use a release tag or commit identifier for --ref.")
    return f"https://github.com/{PUBLIC_REPOSITORY}/archive/{urllib.parse.quote(ref, safe='')}.zip"


def resolve_ref(ref: str = DEFAULT_REF) -> str:
    """Resolve a branch/tag once; download only the resulting immutable revision."""
    archive_url(ref)  # Apply the same ref validation before making a request.
    if re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        return ref.lower()
    url = f"https://api.github.com/repos/{PUBLIC_REPOSITORY}/commits/{urllib.parse.quote(ref, safe='')}"
    # Request the SHA alone: a full commit response can include megabytes of diffs.
    request = urllib.request.Request(url, headers={"User-Agent": "customer-economics-lab-bootstrap/2.0",
                                                 "Accept": "application/vnd.github.sha"})
    with urllib.request.urlopen(request, timeout=30) as response:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "api.github.com":
            raise ValueError("Revision lookup redirected outside the GitHub API.")
        body = response.read(129)
        if len(body) > 128:
            raise ValueError("Revision response exceeds the permitted size.")
    commit = body.decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ValueError("GitHub did not return a full commit SHA; no archive was installed.")
    return commit.lower()


def install_archive(archive: Path, destination: Path) -> Path:
    """Extract one repository root, rejecting traversal, symlinks and overwrites."""
    destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Choose an empty destination; bootstrap never overwrites an existing lab.")
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if sum(entry.file_size for entry in entries) > MAX_EXTRACTED:
            raise ValueError("Archive exceeds the permitted extracted size.")
        roots = set()
        relative_entries = []
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename or ":" in entry.filename:
                raise ValueError("Unsafe archive member path.")
            if not path.parts:
                continue
            roots.add(path.parts[0])
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError("Symlinks are not supported in the lab archive.")
            if len(path.parts) > 1:
                relative_entries.append((entry, Path(*path.parts[1:])))
        if len(roots) != 1:
            raise ValueError("Expected one repository root in the source archive.")
        files = {str(path).replace("\\", "/") for entry, path in relative_entries if not entry.is_dir()}
        if not GUIDED_FILES.issubset(files):
            raise ValueError("Archive is not the guided student edition: missing teaching skill or student entrypoint. Use the current instructor-approved revision.")
        if files & INSTRUCTOR_LAUNCHERS:
            raise ValueError("Archive contains an instructor batch/replay launcher; use the guided student edition.")
        destination.mkdir(parents=True, exist_ok=True)
        for entry, relative in relative_entries:
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Archive member escapes the destination.")
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(entry) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    return destination


def download_lab(destination: Path, ref: str = DEFAULT_REF) -> Path:
    commit = resolve_ref(ref)
    url = archive_url(commit)
    request = urllib.request.Request(url, headers={"User-Agent": "customer-economics-lab-bootstrap/2.0"})
    with tempfile.TemporaryDirectory(prefix="customer-economics-lab-") as temporary:
        archive = Path(temporary) / "lab.zip"
        with urllib.request.urlopen(request, timeout=90) as response, archive.open("wb") as output:
            final = urllib.parse.urlparse(response.geturl())
            if final.scheme != "https" or final.hostname not in {"github.com", "codeload.github.com"}:
                raise ValueError("Archive download redirected outside GitHub HTTPS.")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_DOWNLOAD:
                    raise ValueError("Archive exceeds the permitted download size.")
                output.write(chunk)
        archive_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
        installed = install_archive(archive, destination)
        receipt = {"repository": PUBLIC_REPOSITORY, "requested_ref": ref, "commit": commit,
                   "source_url": url, "archive_sha256": archive_sha256,
                   "entrypoint": "student.py", "mode": "guided-student"}
        (installed / "source_checkout.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return installed


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destination", type=Path, default=Path.cwd() / "customer-economics-lab")
    p.add_argument("--ref", default=DEFAULT_REF, help="Instructor-supplied ref; defaults to main, resolved once to a full commit SHA.")
    args = p.parse_args()
    path = download_lab(args.destination, args.ref)
    print(f"Downloaded the public lab to {path}")
    print("Read SKILL.md and skills/student-teacher/SKILL.md. The pinned revision is in source_checkout.json.")
    print("Introduce Studio North before setup, then use: uv run --frozen python student.py start")
    print('Stop at every checkpoint. Advance once only for the student\'s own "next step" message.')


if __name__ == "__main__":
    main()
