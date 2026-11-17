# Testing

Last checked: **17 November 2026**, Windows x64.

## Offline checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

All **46 tests passed**. They cover syllabus selection, filters, worker state, cancellation, download validation, page order, bookmarks, and preserving existing output on failure.

Both the published **1.1.0** executable and the local **1.2.0** executable passed their packaged `--self-test` checks. The 1.1.0 executable matched the SHA-256 digest supplied by GitHub. The packaged checks use synthetic PDFs, not live downloads.

## Live searches and merges

These checks ran against PapaCambridge. Default searches used 2024–2026, all sessions, and question papers:

| Qualification | Syllabus | Matching PDFs |
| --- | --- | ---: |
| IGCSE | 0580 | 71 |
| AS & A Level | 9709 | 126 |

GUI acceptance checks ran the 1.2.0 source with background catalogue refresh enabled. They invoked the actual **Find papers** and **Save merged PDF…** buttons, waited for the worker queues, and verified the saved PDFs. Native save and notification dialogs were replaced with test callbacks; these were not mouse-driven tests of the packaged executable.

Both GUI checks used **2024**, **May / June**, **Questions + answers**, and exact variant **21**:

| Qualification | Syllabus | Source PDFs | Merged pages |
| --- | --- | ---: | ---: |
| IGCSE | 0580 | 2 | 23 |
| AS & A Level | 9709 | 2 | 29 |

Each output reopened successfully with the expected page count and two filename bookmarks in preview order. No Tk callback errors or application error dialogs occurred.

The reported app failure was **not reproduced**. These checks do not establish that every syllabus, session, repository, network, or Windows configuration works. No app bug fix is claimed from these results.

## Repeat the live check

1. Start the Windows app and note the executable version.
2. Choose IGCSE, enter `0580`, and set both years to `2024`.
3. Set Exam session to **May / June**, Include to **Questions + answers**, and Paper / variant to `21`.
4. Select **Find papers**. Expect `0580_s24_qp_21.pdf` and `0580_s24_ms_21.pdf`.
5. Select **Save merged PDF…**, choose a new destination, and open the result. Check 23 pages and two filename bookmarks.
6. Repeat with AS & A Level and `9709`. Expect the corresponding two filenames and 29 pages.

Repository contents can change. If results differ, record the date, version, exact filters, progress/error text, and original source links. Keep downloaded exam PDFs and local test artifacts out of commits.
