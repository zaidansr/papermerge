"""Download a complete paper selection and publish one validated PDF atomically."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tempfile
import threading
from typing import Callable, Sequence
from urllib.parse import urljoin, urlsplit

import requests
from pypdf import PdfReader, PdfWriter

from .catalog import Paper


class MergeError(RuntimeError):
    """A download or PDF operation failed; no incomplete output is published."""


class CancelledError(MergeError):
    """The user cancelled the operation."""


@dataclass(frozen=True)
class MergeResult:
    path: Path
    paper_count: int
    page_count: int


MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_TOTAL_BYTES = 600 * 1024 * 1024
MAX_PAPERS = 1000
ALLOWED_HOSTS = frozenset({
    "pastpapers.papacambridge.com", "papers.gceguide.com", "papers.gceguide.cc",
    "papers.xtremepape.rs",
})
TRANSIENT_STATUS = frozenset({408, 429, 500, 502, 503, 504})
Progress = Callable[[str, int, int], None]


def _check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise CancelledError("Cancelled. No incomplete PDF was saved.")


def _validate_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        valid = (parts.scheme.lower() == "https" and host in ALLOWED_HOSTS
                 and parts.port in (None, 443) and not parts.username
                 and not parts.password)
    except ValueError:
        valid = False
    if not valid:
        raise MergeError("The source returned an unsupported download address. Refresh the paper list.")
    return url


def _get_response(session: requests.Session, url: str, cancel: threading.Event):
    """Validate each redirect instead of following an arbitrary host automatically."""
    current = _validate_url(url)
    for _ in range(6):
        _check_cancel(cancel)
        response = session.get(current, stream=True, timeout=(15, 25), allow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise MergeError("The paper source returned an empty redirect.")
            current = _validate_url(urljoin(current, location))
            continue
        return response
    raise MergeError("The paper source redirected too many times.")


def _download(session: requests.Session, paper: Paper, target: Path,
              cancel: threading.Event) -> int:
    for attempt in range(3):
        _check_cancel(cancel)
        retry = False
        try:
            with _get_response(session, paper.url, cancel) as response:
                if response.status_code in TRANSIENT_STATUS:
                    if attempt == 2:
                        raise MergeError(f"{paper.filename}: source unavailable (HTTP {response.status_code}). Try again later.")
                    retry = True
                elif response.status_code != 200:
                    raise MergeError(f"{paper.filename}: download failed (HTTP {response.status_code}). Refresh the list or try later.")
                else:
                    length_header = response.headers.get("Content-Length")
                    try:
                        expected = int(length_header) if length_header is not None else None
                    except ValueError:
                        expected = None
                    if expected is not None and (expected < 0 or expected > MAX_FILE_BYTES):
                        raise MergeError(f"{paper.filename}: source file exceeds the 100 MB safety limit.")
                    total = 0
                    with target.open("wb") as stream:
                        for chunk in response.iter_content(chunk_size=128 * 1024):
                            _check_cancel(cancel)
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > MAX_FILE_BYTES:
                                raise MergeError(f"{paper.filename}: source file exceeds the 100 MB safety limit.")
                            stream.write(chunk)
                    encoding = response.headers.get("Content-Encoding", "identity").lower()
                    if expected is not None and encoding in ("", "identity") and total != expected:
                        raise requests.exceptions.ChunkedEncodingError("Incomplete download")
                    with target.open("rb") as stream:
                        header = stream.read(1024)
                        stream.seek(max(0, total - 65536))
                        tail = stream.read()
                    if b"%PDF-" not in header:
                        raise MergeError(f"{paper.filename}: the server returned a web page or invalid file instead of a PDF.")
                    if b"%%EOF" not in tail:
                        raise requests.exceptions.ChunkedEncodingError("Missing PDF end marker")
                    return total
        except requests.RequestException as exc:
            if attempt == 2:
                raise MergeError(f"{paper.filename}: download failed after 3 attempts. Check your connection and try again. ({type(exc).__name__})") from exc
            retry = True
        if retry and cancel.wait(attempt + 1):
            _check_cancel(cancel)
    raise MergeError(f"{paper.filename}: could not download the PDF.")


def _read_pdf(path: Path, filename: str) -> PdfReader:
    try:
        reader = PdfReader(path, strict=False)
        if reader.is_encrypted:
            reader.close()
            raise MergeError(f"{filename}: encrypted PDFs cannot be merged.")
        if not len(reader.pages):
            reader.close()
            raise MergeError(f"{filename}: PDF contains no pages.")
        return reader
    except MergeError:
        raise
    except Exception as exc:
        raise MergeError(f"{filename}: PDF is damaged or unreadable. No merged PDF was saved.") from exc


def build_pdf(papers: Sequence[Paper], output: Path, cancel: threading.Event,
              progress: Progress) -> MergeResult:
    """Merge every selected paper, or leave the destination completely unchanged.

    Network and PDF work belongs on a worker thread. ``progress`` must marshal any
    UI updates to the GUI thread. Paper order is the caller's preview order.
    """
    selection = tuple(papers)
    _check_cancel(cancel)
    if not selection:
        raise MergeError("Select at least one paper to download and merge.")
    if len(selection) > MAX_PAPERS:
        raise MergeError("Choose at most 1,000 files per PDF. Narrow the year range or components.")
    if len({paper.filename.casefold() for paper in selection}) != len(selection):
        raise MergeError("The selection contains duplicate filenames. Refresh the paper list.")
    output = Path(output).expanduser().absolute()
    if output.suffix.lower() != ".pdf":
        raise MergeError("The output filename must end in .pdf.")
    if output.is_dir():
        raise MergeError("The output location is a folder. Choose a PDF filename.")
    for paper in selection:
        _validate_url(paper.url)
    count = len(selection)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".papermerge-", dir=output.parent) as temp:
            tempdir = Path(temp)
            downloaded: list[Path] = []
            total_bytes = 0
            with requests.Session() as session:
                session.headers.update({
                    "User-Agent": "PaperMerge/1.0 (personal study PDF downloader)",
                    "Accept": "application/pdf,*/*;q=0.8",
                    "Accept-Encoding": "identity",
                })
                for index, paper in enumerate(selection):
                    _check_cancel(cancel)
                    progress(f"Downloading {index + 1}/{count}: {paper.filename}", index, count)
                    target = tempdir / f"{index:05d}.pdf"
                    total_bytes += _download(session, paper, target, cancel)
                    if total_bytes > MAX_TOTAL_BYTES:
                        raise MergeError("This selection exceeds 600 MB. Narrow the year range or components.")
                    downloaded.append(target)
            writer = PdfWriter()
            page_count = 0
            readers: list[PdfReader] = []
            try:
                for index, (paper, path) in enumerate(zip(selection, downloaded)):
                    _check_cancel(cancel)
                    progress(f"Merging {index + 1}/{count}: {paper.filename}", index, count)
                    reader = _read_pdf(path, paper.filename)
                    readers.append(reader)
                    try:
                        page_count += len(reader.pages)
                        writer.append(reader, outline_item=paper.filename, import_outline=False)
                    except Exception as exc:
                        raise MergeError(f"{paper.filename}: PDF could not be merged. No output was replaced.") from exc
                writer.add_metadata({
                    "/Title": f"Cambridge {selection[0].code} past papers",
                    "/Author": "Original paper publishers",
                    "/Creator": "PaperMerge",
                    "/Subject": f"{count} source PDFs; bookmarks identify each original filename. Sources: "
                                + ", ".join(sorted({p.source for p in selection})),
                })
                _check_cancel(cancel)
                progress("Writing and verifying the merged PDF...", count, count)
                candidate = tempdir / "merged.pdf"
                with candidate.open("wb") as stream:
                    writer.write(stream)
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                writer.close()
                for reader in readers:
                    reader.close()
            _check_cancel(cancel)
            with candidate.open("rb") as stream:
                verified = PdfReader(stream, strict=True)
                if len(verified.pages) != page_count or len(verified.outline) != count:
                    raise MergeError("The merged PDF did not pass verification. No output was replaced.")
                if [item.title for item in verified.outline] != [p.filename for p in selection]:
                    raise MergeError("The merged PDF bookmarks did not pass verification. No output was replaced.")
            _check_cancel(cancel)
            os.replace(candidate, output)
            return MergeResult(output, count, page_count)
    except (MergeError, CancelledError):
        raise
    except PermissionError as exc:
        raise MergeError("Cannot save the PDF. Close it in your PDF viewer, or choose a writable output folder.") from exc
    except OSError as exc:
        raise MergeError(f"Cannot create the PDF. Check free disk space and the output folder. ({exc.strerror or type(exc).__name__})") from exc
    except Exception as exc:
        raise MergeError(f"The PDF operation failed ({type(exc).__name__}). No incomplete PDF was saved.") from exc
