# PaperMerge

**[Use PaperMerge in your browser](https://zaidansr.github.io/papermerge/)** · [Download the Windows app](https://github.com/zaidansr/papermerge/releases/latest)

## Browser version

The GitHub Pages website searches all bundled subjects, links to the original paper catalogues, and combines PDFs selected from your device. Choose files, use Up/Down to arrange them, then select **Merge & download**. Files stay in browser memory and are never uploaded. Clearing the page removes the selected files from the app.

GitHub Pages is static hosting. Repository browser-access restrictions mean it cannot automatically fetch exam PDFs: download them from the linked catalogue first, then select them in the web tool. The Windows app supports automatic discovery, downloading, and merging.

The web merger accepts up to 100 PDFs, 50 MB each and 150 MB total. Locked or damaged PDFs are rejected; original bookmarks and interactive form behaviour may not survive merging. PDF-Lib 1.17.1 loads from a pinned CDN URL with an integrity hash, so an internet connection is required to load the tool.

Web source is in `docs/` and requires no build step. GitHub Pages publishes `main` → `/docs`. For local preview, run `python -m http.server 8766 --directory docs`. To run the six web merge/catalogue checks with Node.js 20+ and npm: `npm install --ignore-scripts`, then `npm run test:web`.

[![Windows build](https://github.com/zaidansr/papermerge/actions/workflows/windows.yml/badge.svg)](https://github.com/zaidansr/papermerge/actions/workflows/windows.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Download Cambridge IGCSE and AS & A Level past papers by syllabus, then combine your selection into one bookmarked PDF. PaperMerge is a portable Windows desktop app with a searchable subject dropdown.

**[Download the latest Windows release](https://github.com/zaidansr/papermerge/releases/latest)** · [Report a problem](https://github.com/zaidansr/papermerge/issues/new?template=bug_report.md)

## Features

Version 1.2 adds a monochrome iOS-inspired Windows interface, a Top 20 subjects collection for each qualification, dropdowns for years/sessions/document types/papers, and results search. Top 20 is curated and includes archived codes; it is not an official popularity ranking.

- Search syllabus codes and subject names; switch between IGCSE and AS & A Level.
- Browse a bundled catalogue of **148 IGCSE** and **110 AS & A Level** codes, including archived syllabuses. Refresh from the source on demand or automatically at startup.
- Filter by year, exam session, document type, and component variant.
- Include question papers, mark schemes, inserts, instructions, examiner reports, and grade thresholds.
- Review every file in merge order and include or exclude individual papers.
- Preserve original page sizes, orientation, text, and links; add a bookmark for each source filename.
- Validate downloads and preserve an existing output if an operation fails or is cancelled.

## Download and run

1. Open the [latest release](https://github.com/zaidansr/papermerge/releases/latest).
2. Download and extract the Windows x64 ZIP. It includes the app, README, MIT license, third-party notices, and an executable SHA-256 checksum.
3. Open `PaperMerge-v1.2.0.exe` (or the corresponding newer version).

The app needs **Windows 10/11, 64-bit**. Python and administrator privileges are not required. An internet connection is required to find and download papers. The executable is unsigned.

## Use

1. Choose **IGCSE** or **AS & A Level**.
2. Open the **Syllabus** dropdown. Each entry shows a code and subject name, such as `0580 — Mathematics`. Type a code or part of a name to narrow the list, then select an entry. Clear the box to show the full list again.
3. Choose years, sessions, and document types. **Question papers** are selected by default; select **Mark schemes** to include answers.
4. Optionally enter components. `2` includes paper 2 and variants such as 21, 22, and 23. `21,22` includes those exact variants. Leave blank for all. Selected session-wide reports and thresholds are included regardless of this filter.
5. Click **Find papers**, review the preview, and click rows or press Space to include or exclude files.
6. Click **Download & merge PDF**, choose a destination, and wait for confirmation. **Open PDF** opens the result in your default viewer.

Files are merged by year, session, and component, in preview order. Within a component the order is question paper, insert, instructions, then mark scheme. Reports and thresholds follow component files.

Cancellation can take until the current network request finishes. Temporary downloads are removed after success, failure, or normal cancellation. A forced process termination can leave a `.papermerge-` temporary folder beside the chosen output.

## Sources and availability

PaperMerge reads actual published links from [PapaCambridge](https://pastpapers.papacambridge.com/), with [GCE Guide](https://papers.gceguide.com/) as a fallback. It does not guess PDF addresses or bypass access restrictions.

The bundled catalogue was fetched on **28 October 2026**. It includes archived subjects; a listed code does not guarantee papers for every year, session, or variant. The app cannot supply unpublished, withdrawn, or unlisted papers. Audio, ZIP files, specimen papers, and nonstandard PDF filenames are excluded.

If a search is empty, check the qualification, code, years, sessions, and components. If a repository is unavailable, blocks access, or changes its layout, the app reports the problem. Try later or use the source website. Live repository availability is separate from the offline tests.

Per merge: **1,000 files maximum**, **100 MB per file**, and **600 MB total downloaded material**. Large selections also need sufficient memory and free disk space.

## Run from source

Use Python **3.13 x64 with Tcl/Tk** on Windows. From the repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The 46 offline tests cover exact syllabus matching, leading zeros, catalogue parsing and fallback, dropdown search, qualification switching, stale refresh replies, PDF order, text/rotation/link preservation, bookmarks, retries, invalid downloads, cancellation, and protecting existing output. Widget tests create hidden Tk windows; run them in a Windows desktop session.

The executable also has an offline smoke test:

```powershell
.\PaperMerge-v1.2.0.exe --self-test .\smoke-test
```

It writes `self-test.json` and a two-page `smoke.pdf`, verifying the packaged dropdown, bundled catalogues, and PDF engine.

## Build a Windows release

```powershell
.\build.ps1 -Python (Get-Command python).Source
```

The script creates a private environment, installs pinned dependencies, runs tests, builds a single-file executable using PyInstaller, verifies its smoke test, and creates a ZIP with licenses and a SHA-256 checksum in `dist/`. No compiler is required. The [Windows workflow](.github/workflows/windows.yml) runs the same checks and uploads build artifacts.

## Project layout

| Path | Purpose |
| --- | --- |
| `main.py` | Desktop and smoke-test entry point |
| `papermerge/catalog.py` | Paper discovery and filtering |
| `papermerge/syllabuses.py` | Live and bundled subject catalogues |
| `papermerge/engine.py` | Download validation and atomic PDF merging |
| `papermerge/gui.py` | Tk interface and worker queues |
| `assets/syllabuses.json` | Bundled catalogue and source/date metadata |
| `tests/` | Offline unit and widget acceptance tests |
| `build.ps1` | Windows test, package, and release script |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports should include the version, qualification, syllabus code, filters, and exact error message. Keep downloaded exam material, environments, and build output out of commits.

## License and attribution

PaperMerge's original source code is released under the **[MIT License](LICENSE)**, copyright © 2026 zaidansr.

Third-party software retains its own licenses; see [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt). Downloaded exam materials remain the property of their respective publishers and are **not covered by PaperMerge's MIT license**. No exam PDFs are distributed in this repository or releases.

This independent project is not affiliated with, endorsed by, or maintained by Cambridge International Education, PapaCambridge, or GCE Guide.

