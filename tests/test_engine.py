"""Checks that failed or cancelled downloads can never publish partial output."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import requests
from pypdf import PdfReader, PdfWriter

from papermerge.catalog import Paper
from papermerge.engine import CancelledError, MergeError, build_pdf


def pdf_bytes(widths=(100,), encrypted=False):
    writer = PdfWriter()
    for width in widths:
        writer.add_blank_page(width=width, height=200)
    if encrypted:
        writer.encrypt("secret")
    stream = BytesIO()
    writer.write(stream)
    writer.close()
    return stream.getvalue()


def paper(filename="0580_s24_qp_11.pdf", kind="qp"):
    return Paper(code="0580", year=2024, session="s", kind=kind,
                 component="11", filename=filename,
                 url=f"https://pastpapers.papacambridge.com/directories/{filename}",
                 source="PapaCambridge")


class FastEvent(threading.Event):
    def wait(self, timeout=None):
        return self.is_set()


class Response:
    def __init__(self, data=b"", status=200, headers=None):
        self.data = data
        self.status_code = status
        self.headers = headers if headers is not None else {"Content-Length": str(len(data))}
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.closed = True

    def iter_content(self, chunk_size):
        yield self.data


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.headers = {}
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def get(self, *args, **kwargs):
        self.calls += 1
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.output = self.folder / "papers.pdf"
        self.cancel = FastEvent()

    def build(self, papers, responses, progress=lambda *args: None):
        session = Session(responses)
        with patch("papermerge.engine.requests.Session", return_value=session):
            result = build_pdf(papers, self.output, self.cancel, progress)
        return result, session

    def assert_no_temporary_files(self):
        self.assertEqual(list(self.folder.glob(".papermerge-*")), [])

    def test_every_page_retains_input_order_and_filename_bookmarks(self):
        papers = [paper(), paper("0580_s24_ms_11.pdf", "ms")]
        result, _ = self.build(papers, [Response(pdf_bytes((101, 102))), Response(pdf_bytes((201,)))])
        self.assertEqual((result.paper_count, result.page_count), (2, 3))
        with self.output.open("rb") as stream:
            reader = PdfReader(stream, strict=True)
            self.assertEqual([float(p.mediabox.width) for p in reader.pages], [101, 102, 201])
            self.assertEqual([p.title for p in reader.outline], [p.filename for p in papers])
            self.assertEqual(reader.get_destination_page_number(reader.outline[1]), 2)
        self.assert_no_temporary_files()

    def test_later_download_failure_preserves_existing_destination(self):
        original = pdf_bytes((333,))
        self.output.write_bytes(original)
        with self.assertRaisesRegex(MergeError, "HTTP 404"):
            self.build([paper(), paper("0580_s24_ms_11.pdf")], [Response(pdf_bytes()), Response(status=404)])
        self.assertEqual(self.output.read_bytes(), original)
        self.assert_no_temporary_files()

    def test_cancelled_before_start_creates_nothing(self):
        self.cancel.set()
        with self.assertRaises(CancelledError):
            self.build([paper()], [])
        self.assertFalse(self.output.exists())
        self.assert_no_temporary_files()

    def test_cancel_during_merge_does_not_replace_output(self):
        self.output.write_bytes(b"existing file")
        def on_progress(message, *_):
            if message.startswith("Merging"):
                self.cancel.set()
        with self.assertRaises(CancelledError):
            self.build([paper()], [Response(pdf_bytes())], on_progress)
        self.assertEqual(self.output.read_bytes(), b"existing file")
        self.assert_no_temporary_files()

    def test_html_response_is_never_saved_as_a_pdf(self):
        with self.assertRaisesRegex(MergeError, "instead of a PDF"):
            self.build([paper()], [Response(b"<html>Access denied</html>")])
        self.assertFalse(self.output.exists())
        self.assert_no_temporary_files()

    def test_truncated_download_retries_then_fails_without_output(self):
        truncated = pdf_bytes()[:-30]
        with self.assertRaisesRegex(MergeError, "3 attempts"):
            self.build([paper()], [Response(truncated) for _ in range(3)])
        self.assertFalse(self.output.exists())
        self.assert_no_temporary_files()

    def test_corrupt_pdf_cannot_publish_output(self):
        with self.assertRaisesRegex(MergeError, "damaged or unreadable"):
            self.build([paper()], [Response(b"%PDF-1.7\ncorrupt\n%%EOF\n")])
        self.assertFalse(self.output.exists())
        self.assert_no_temporary_files()

    def test_encrypted_pdf_is_rejected(self):
        with self.assertRaisesRegex(MergeError, "encrypted"):
            self.build([paper()], [Response(pdf_bytes(encrypted=True))])
        self.assertFalse(self.output.exists())

    def test_empty_pdf_is_rejected(self):
        with self.assertRaisesRegex(MergeError, "no pages"):
            self.build([paper()], [Response(pdf_bytes(()))])
        self.assertFalse(self.output.exists())

    def test_transient_network_error_can_recover(self):
        result, session = self.build([paper()], [requests.ConnectionError("temporary"), Response(pdf_bytes())])
        self.assertEqual(session.calls, 2)
        self.assertEqual(result.page_count, 1)

    def test_untrusted_redirect_is_rejected_before_following(self):
        response = Response(status=302, headers={"Location": "https://example.org/file.pdf"})
        with self.assertRaisesRegex(MergeError, "unsupported download address"):
            self.build([paper()], [response])
        self.assertTrue(response.closed)
        self.assertFalse(self.output.exists())

    def test_save_permission_error_preserves_existing_file(self):
        self.output.write_bytes(b"keep me")
        with patch("papermerge.engine.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaisesRegex(MergeError, "Close it in your PDF viewer"):
                self.build([paper()], [Response(pdf_bytes())])
        self.assertEqual(self.output.read_bytes(), b"keep me")
        self.assert_no_temporary_files()

    def test_duplicate_selection_is_rejected(self):
        with self.assertRaisesRegex(MergeError, "duplicate"):
            self.build([paper(), paper()], [])
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
