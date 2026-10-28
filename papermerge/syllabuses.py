"""Qualification syllabus lists for the searchable desktop dropdown.

Entries describe repository catalogues, including archived qualifications. They
do not assert that a syllabus is offered in the current examination year.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
import threading
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit

import requests

from .catalog import (PAPA, GCE, CatalogError, Cancelled, _check_cancel,
                      _get_html, _papa_link, links_from_html)

QUALIFICATIONS = ("IGCSE", "AS & A Level")
_CODE = re.compile(r"(?<![0-9])([0-9]{4})(?![0-9])")


@dataclass(frozen=True)
class Syllabus:
    code: str
    title: str
    qualification: str

    @property
    def label(self) -> str:
        return f"{self.code} — {self.title}"


def _validate_qualification(qualification: str) -> None:
    if qualification not in QUALIFICATIONS:
        raise ValueError("Choose IGCSE or AS & A Level.")


def _title(label: str, code: str, slug: str = "") -> str:
    # Prefer the repository's human-readable label over its URL slug.
    value = label.strip() or slug.replace("-", " ")
    value = re.sub(rf"\(\s*{re.escape(code)}\s*\)", "", value)
    value = re.sub(rf"(?<![0-9]){re.escape(code)}(?![0-9])", "", value)
    value = re.sub(r"\s*[-–—]+\s*(?=$)", "", value)
    value = re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z])", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -–—")
    # A code followed by a region flag may leave duplicate separators.
    value = re.sub(r"(?:\s*[-–—]\s*){2,}", " - ", value)
    return value


def _deduplicate(entries: list[Syllabus]) -> list[Syllabus]:
    unique: dict[str, Syllabus] = {}
    for entry in entries:
        if _CODE.fullmatch(entry.code) and entry.title:
            previous = unique.get(entry.code)
            # Duplicated navigation cards sometimes omit the descriptive title.
            if previous is None or len(entry.title) > len(previous.title):
                unique[entry.code] = entry
    return sorted(unique.values(), key=lambda item: (item.title.casefold(), item.code))


def parse_papa_syllabuses(html: str, qualification: str) -> list[Syllabus]:
    _validate_qualification(qualification)
    slug = "igcse" if qualification == "IGCSE" else "as-and-a-level"
    prefix = f"/papers/caie/{slug}-"
    entries = []
    for href, label in links_from_html(html):
        try:
            url = _papa_link(href)
        except (CatalogError, ValueError):
            continue
        if not url:
            continue
        parts = urlsplit(url)
        path = unquote(parts.path).rstrip("/")
        if not path.startswith(prefix) or parts.query:
            continue
        remainder = path[len(prefix):]
        # Session and editorial links are not syllabus index entries.
        if re.search(r"(?:^|-)(?:19|20)[0-9]{2}(?:-|$)", remainder):
            continue
        path_codes = _CODE.findall(remainder)
        if len(set(path_codes)) != 1:
            continue
        code = path_codes[0]
        label_codes = _CODE.findall(label)
        if label_codes and code not in label_codes:
            continue
        title = _title(label, code, remainder)
        if title:
            entries.append(Syllabus(code, title, qualification))
    result = _deduplicate(entries)
    if not result:
        raise CatalogError("The syllabus catalogue contained no recognisable subjects. The repository layout may have changed.")
    return result


def parse_gce_syllabuses(html: str, qualification: str) -> list[Syllabus]:
    _validate_qualification(qualification)
    folder = "IGCSE" if qualification == "IGCSE" else "A%20Levels"
    base = f"{GCE}/{folder}/"
    entries = []
    for href, label in links_from_html(html):
        url = urljoin(base, href)
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname != urlsplit(GCE).hostname or parts.query:
            continue
        if not parts.path.startswith(urlsplit(base).path):
            continue
        remainder = unquote(parts.path[len(urlsplit(base).path):]).strip("/")
        if not remainder or "/" in remainder:
            continue
        codes = _CODE.findall(remainder)
        if len(set(codes)) != 1:
            continue
        code = codes[0]
        title = _title(label.rstrip("/"), code, remainder)
        if title:
            entries.append(Syllabus(code, title, qualification))
    result = _deduplicate(entries)
    if not result:
        raise CatalogError("The fallback syllabus catalogue contained no recognisable subjects.")
    return result


def list_syllabuses(qualification: str, cancel: threading.Event,
                   progress: Callable[[str], None]) -> list[Syllabus]:
    """Fetch the selected qualification's full repository subject catalogue."""
    _validate_qualification(qualification)
    slug = "igcse" if qualification == "IGCSE" else "as-and-a-level"
    folder = "IGCSE" if qualification == "IGCSE" else "A%20Levels"
    providers = ((f"{PAPA}/papers/caie/{slug}", parse_papa_syllabuses, "PapaCambridge"),
                 (f"{GCE}/{folder}/", parse_gce_syllabuses, "GCE Guide"))
    errors = []
    for url, parser, source in providers:
        _check_cancel(cancel)
        progress(f"Loading {qualification} syllabus list from {source}...")
        try:
            entries = parser(_get_html(url, cancel), qualification)
            _check_cancel(cancel)
            progress(f"Loaded {len(entries)} {qualification} syllabuses.")
            return entries
        except Cancelled:
            raise
        except (CatalogError, requests.RequestException) as exc:
            errors.append(f"{source}: {exc}")
    raise CatalogError("Could not refresh the syllabus list.\n\n" + "\n\n".join(errors))


def load_bundled(qualification: str) -> list[Syllabus]:
    """Load the last verified catalogue snapshot, requiring no network access."""
    _validate_qualification(qualification)
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    path = root / "assets" / "syllabuses.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = [Syllabus(str(item["code"]), str(item["title"]), qualification)
                   for item in data["qualifications"][qualification]
                   if isinstance(item, dict)]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return _deduplicate(entries)
