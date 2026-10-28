"""Discover published Cambridge PDFs from public repository listings.

PDF addresses are read from repository links, never inferred from file patterns.
The PapaCambridge adapter handles its nonstandard root-relative links and nested
download URLs. The GCE Guide adapter is a fallback for ordinary directory indexes.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import date
from html import unescape
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import requests


class CatalogError(RuntimeError):
    """A repository could not provide a complete listing for this search."""


class Cancelled(CatalogError):
    """The user cancelled discovery."""


@dataclass(frozen=True)
class Paper:
    code: str
    year: int
    session: str
    kind: str
    component: str
    filename: str
    url: str
    source: str


PAPA = "https://pastpapers.papacambridge.com"
GCE = "https://papers.gceguide.com"
USER_AGENT = "PaperMerge/1.0 (personal educational paper collection)"
TIMEOUT = (8, 20)
MAX_LISTING_BYTES = 6 * 1024 * 1024
_FILE = re.compile(
    r"^(?P<code>[0-9]{4})_(?P<session>[msw])(?P<year>[0-9]{2})_"
    r"(?P<kind>[a-z]{2,4})(?:_(?P<component>[0-9]{1,2}(?:\+[0-9]{1,2})*))?"
    r"(?:_[a-z0-9]+)*\.pdf$", re.I,
)
_KIND_ORDER = {"qp": 0, "in": 1, "ci": 2, "ms": 3, "gt": 4, "er": 5}


def validate_code(code: str) -> str:
    code = str(code).strip()
    if not re.fullmatch(r"[0-9]{4}", code):
        raise ValueError("Enter the four-digit syllabus code, including a leading zero (for example 0580).")
    return code


def paper_sort_key(paper: Paper) -> tuple:
    return (paper.year, {"m": 0, "s": 1, "w": 2}[paper.session],
            int(paper.component.split("+")[0]) if paper.component else 1000,
            paper.component, _KIND_ORDER.get(paper.kind, 10), paper.filename)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((unescape(self._href).strip(), " ".join(self._text).strip()))
            self._href = None


def links_from_html(html: str) -> list[tuple[str, str]]:
    parser = _Links()
    parser.feed(html)
    parser.close()
    return parser.links


def _check_cancel(cancel: threading.Event):
    if cancel.is_set():
        raise Cancelled("Search cancelled.")


def _safe_url(url: str, host: str) -> str:
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != host or parts.username
            or parts.password or parts.port not in (None, 443)):
        raise CatalogError("The repository returned an unexpected external link.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _get_html(url: str, cancel: threading.Event) -> str:
    host = urlsplit(url).hostname
    last_error = None
    with requests.Session() as client:
        client.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html"})
        for attempt in range(2):
            _check_cancel(cancel)
            try:
                current = _safe_url(url, host)
                for _ in range(5):
                    response = client.get(current, timeout=TIMEOUT, stream=True, allow_redirects=False)
                    if response.is_redirect:
                        destination = _safe_url(urljoin(current, response.headers.get("Location", "")), host)
                        response.close()
                        current = destination
                        continue
                    break
                else:
                    raise CatalogError("Too many repository redirects.")
                with response:
                    if response.status_code in (403, 401):
                        raise CatalogError("The repository is blocking automated access. Try again later or use its website.")
                    if response.status_code == 404:
                        raise CatalogError("The repository listing is no longer available (HTTP 404).")
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        _check_cancel(cancel)
                        size += len(chunk)
                        if size > MAX_LISTING_BYTES:
                            raise CatalogError("The repository listing exceeded the safe size limit.")
                        chunks.append(chunk)
                    html = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                    if not html.strip():
                        raise CatalogError("The repository returned an empty listing.")
                    return html
            except (requests.RequestException, CatalogError) as exc:
                if isinstance(exc, Cancelled):
                    raise
                last_error = exc
                # Access denials and parsing problems will not improve on retry.
                if isinstance(exc, CatalogError):
                    break
                if attempt == 0 and cancel.wait(0.6):
                    raise Cancelled("Search cancelled.")
    if isinstance(last_error, CatalogError):
        raise last_error
    raise CatalogError(f"Could not reach {host}. Check your internet connection. {last_error}") from last_error


def _papa_link(href: str) -> str | None:
    href = unescape(href).strip()
    if not href or href.startswith(("#", "javascript:", "mailto:")):
        return None
    # PapaCambridge uses 'papers/caie/...' relative to the domain, not page.
    if href.startswith(("papers/", "viewer/", "directories/")):
        href = "/" + href
    url = urljoin(PAPA + "/", href)
    if urlsplit(url).hostname != urlsplit(PAPA).hostname:
        return None
    # Older editorial links contain a duplicated prefix.
    url = url.replace("/papers/caie/papers/caie/", "/papers/caie/")
    return _safe_url(url, urlsplit(PAPA).hostname)


def parse_paper_link(url: str, source: str, expected_code: str | None = None) -> Paper | None:
    """Return metadata only for standard, named past-paper PDFs."""
    parts = urlsplit(url)
    # Unquote without form-style '+' decoding: old combined mark schemes have
    # literal '+' characters in their filenames (for example ms_1+2.pdf).
    nested = re.search(r"(?:^|&)files=([^&]+)", parts.query)
    if nested:
        url = unquote(nested[1])
        parts = urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password:
        return None
    filename = unquote(parts.path.rsplit("/", 1)[-1]).lower()
    match = _FILE.fullmatch(filename)
    if not match or (expected_code and match["code"] != expected_code):
        return None
    short_year = int(match["year"])
    year = 1900 + short_year if short_year >= 80 else 2000 + short_year
    return Paper(match["code"], year, match["session"].lower(), match["kind"].lower(),
                 match["component"] or "", filename, url, source)


def _page_session(label: str) -> tuple[int, str] | None:
    year = re.search(r"(?<![0-9])((?:19|20)[0-9]{2})(?![0-9])", label)
    if not year:
        return None
    label = label.lower()
    if re.search(r"\b(?:march|mar|february|feb)\b", label):
        season = "m"
    elif re.search(r"\b(?:june|jun|may)\b", label):
        season = "s"
    elif re.search(r"\b(?:november|nov|october|oct)\b", label):
        season = "w"
    else:
        return None
    return int(year[1]), season


def _from_papa(code, qualification, start_year, end_year, sessions, cancel, progress):
    slug = "igcse" if qualification == "IGCSE" else "as-and-a-level"
    progress("Connecting to PapaCambridge syllabus catalogue...")
    index = _get_html(f"{PAPA}/papers/caie/{slug}", cancel)
    subject_urls = []
    for href, label in links_from_html(index):
        url = _papa_link(href)
        if not url:
            continue
        path = unquote(urlsplit(url).path)
        if (path.startswith(f"/papers/caie/{slug}-")
                and re.search(rf"(?<![0-9]){re.escape(code)}(?![0-9])", path + " " + label)
                and not re.search(r"-(?:19|20)[0-9]{2}-", path)):
            if url not in subject_urls:
                subject_urls.append(url)
    if not subject_urls:
        raise CatalogError(f"Syllabus {code} was not found in the {qualification} catalogue. Check the code and qualification.")
    papers, seen_pages = [], set()
    for subject_url in subject_urls:
        _check_cancel(cancel)
        progress(f"Reading published sessions for {code}...")
        subject = _get_html(subject_url, cancel)
        pages = []
        recognised_sessions = set()
        for href, label in links_from_html(subject):
            url = _papa_link(href)
            if not url or url in seen_pages:
                continue
            parts = urlsplit(url)
            if parts.fragment or not parts.path.startswith(urlsplit(subject_url).path + "-"):
                continue
            session = _page_session(label) or _page_session(unquote(parts.path).replace("-", " "))
            if session:
                recognised_sessions.add(session)
            if session and start_year <= session[0] <= end_year and session[1] in sessions:
                seen_pages.add(url)
                pages.append((session, url))
        if not recognised_sessions:
            raise CatalogError(f"The syllabus {code} page contained no recognisable exam sessions. It may be empty or the repository layout may have changed.")
        for (year, season), page_url in sorted(pages):
            _check_cancel(cancel)
            progress(f"Reading {code}: {year} { {'m': 'Feb/Mar', 's': 'May/Jun', 'w': 'Oct/Nov'}[season] }...")
            html = _get_html(page_url, cancel)
            found = []
            for href, _ in links_from_html(html):
                url = _papa_link(href)
                if not url:
                    continue
                paper = parse_paper_link(url, "PapaCambridge", code)
                if (paper and paper.year == year and paper.session == season
                        and urlsplit(paper.url).hostname == urlsplit(PAPA).hostname):
                    found.append(paper)
            if not found:
                raise CatalogError(f"The {year} session listing contained no recognisable PDFs. The repository may have changed.")
            papers.extend(found)
    return papers


def _from_gce(code, qualification, start_year, end_year, sessions, cancel, progress):
    folder = "IGCSE" if qualification == "IGCSE" else "A%20Levels"
    base = f"{GCE}/{folder}/"
    progress("Trying the GCE Guide repository...")
    index = _get_html(base, cancel)
    subject_urls = []
    for href, label in links_from_html(index):
        url = urljoin(base, href)
        if (url.startswith(base) and urlsplit(url).hostname == urlsplit(GCE).hostname
                and re.search(rf"(?<![0-9]){re.escape(code)}(?![0-9])", unquote(url) + " " + label)):
            if url not in subject_urls:
                subject_urls.append(url)
    if not subject_urls:
        raise CatalogError(f"Syllabus {code} was not found in the GCE Guide {qualification} catalogue.")
    papers = []
    for subject in subject_urls:
        html = _get_html(subject, cancel)
        pages = {subject: html}
        for href, label in links_from_html(html):
            url = urljoin(subject, href)
            year = re.fullmatch(r"(?:19|20)[0-9]{2}", label.strip().strip("/"))
            if not year:
                year = re.fullmatch(r"(?:19|20)[0-9]{2}", urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])
            if (year and start_year <= int(year[0]) <= end_year
                    and url.startswith(subject) and urlsplit(url).hostname == urlsplit(GCE).hostname):
                progress(f"Reading {code}: {year[0]} from GCE Guide...")
                pages[url] = _get_html(url, cancel)
        for page_url, listing in pages.items():
            for href, _ in links_from_html(listing):
                url = urljoin(page_url, href)
                if urlsplit(url).hostname != urlsplit(GCE).hostname:
                    continue
                paper = parse_paper_link(url, "GCE Guide", code)
                if paper:
                    papers.append(paper)
    return papers


def _component_matches(component: str, selected: set[str]) -> bool:
    # Session-wide reports/thresholds have no paper component.
    if not selected or not component:
        return True
    return any(part == wanted or (len(wanted) == 1 and part.startswith(wanted))
               for part in component.split("+") for wanted in selected)


def discover(code: str, qualification: str, start_year: int, end_year: int,
             sessions: set[str], kinds: set[str], components: set[str],
             cancel: threading.Event, progress: Callable[[str], None]) -> list[Paper]:
    code = validate_code(code)
    if qualification not in ("IGCSE", "AS & A Level"):
        raise ValueError("Choose IGCSE or AS & A Level.")
    current_year = date.today().year
    if not (1980 <= start_year <= end_year <= current_year):
        raise ValueError(f"Choose a year range from 1980 to {current_year}, with the start before the end.")
    sessions, kinds, components = set(sessions), set(kinds), set(components)
    if not sessions or not sessions <= {"m", "s", "w"}:
        raise ValueError("Select at least one exam session.")
    if not kinds or any(not re.fullmatch(r"[a-z]{2,4}", kind) for kind in kinds):
        raise ValueError("Select at least one PDF document type.")
    if any(not re.fullmatch(r"[0-9]{1,2}", component) for component in components):
        raise ValueError("Components must contain one or two digits, for example 2, 21, 22.")
    errors = []
    for provider in (_from_papa, _from_gce):
        _check_cancel(cancel)
        try:
            papers = provider(code, qualification, start_year, end_year, sessions, cancel, progress)
        except Cancelled:
            raise
        except (CatalogError, requests.RequestException) as exc:
            errors.append(str(exc))
            progress(str(exc))
            continue
        # A successful listing with no matching papers is a real empty search,
        # not a reason to substitute uncertain results from another repository.
        unique = {}
        for paper in papers:
            if (start_year <= paper.year <= end_year and paper.session in sessions
                    and paper.kind in kinds and _component_matches(paper.component, components)):
                unique.setdefault(paper.filename, paper)
        result = sorted(unique.values(), key=paper_sort_key)
        progress(f"Found {len(result)} matching PDFs.")
        return result
    raise CatalogError("Search could not be completed. No partial listing was used.\n\n" + "\n\n".join(errors))
