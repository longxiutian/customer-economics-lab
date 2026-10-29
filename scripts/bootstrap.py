#!/usr/bin/env python3
"""Download a public lab archive over HTTPS without Git or authentication."""
from __future__ import annotations

import argparse
import shutil
import stat
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

PUBLIC_REPOSITORY = "longxiutian/customer-economics-lab"
DEFAULT_REF = "v4.0.0"
MAX_DOWNLOAD = 128 * 1024 * 1024
MAX_EXTRACTED = 512 * 1024 * 1024


def archive_url(ref: str = DEFAULT_REF) -> str:
    if not ref or any(character in ref for character in ("\\", "?", "#", "..")):
        raise ValueError("Use a release tag or commit identifier for --ref.")
    return f"https://github.com/{PUBLIC_REPOSITORY}/archive/{urllib.parse.quote(ref, safe='')}.zip"


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
        if not {"SKILL.md", "lab.py", "pyproject.toml"}.issubset(files):
            raise ValueError("Archive is missing the lab entrypoint, skill, or environment definition.")
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
    request = urllib.request.Request(archive_url(ref), headers={"User-Agent": "customer-economics-lab-bootstrap/1.0"})
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
        return install_archive(archive, destination)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destination", type=Path, default=Path.cwd() / "customer-economics-lab")
    p.add_argument("--ref", default=DEFAULT_REF, help="Public release tag or commit; defaults to the frozen classroom release.")
    args = p.parse_args()
    path = download_lab(args.destination, args.ref)
    print(f"Downloaded the public lab to {path}")
    print("Read SKILL.md in that folder. No Git installation or GitHub account is required.")
    print("Complete docs/setup.md before class, then use: uv run --frozen python lab.py start")


if __name__ == "__main__":
    main()
