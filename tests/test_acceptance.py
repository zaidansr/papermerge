"""Independent acceptance checks for preserving paper contents and aborting safely."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                           FloatObject, NameObject, NumberObject, TextStringObject)

from papermerge.catalog import CatalogError, Paper, discover, parse_paper_link, validate_code
from papermerge.engine import CancelledError, MergeError, build_pdf


def text_pdf(text: str, width: int, height: int, rotation: int = 0) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
        NameObject("/F1"): writer._add_object(font)})})
    contents = DecodedStreamObject()
    contents.set_data(f"BT /F1 14 Tf 20 30 Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(contents)
    if rotation:
        page.rotate(rotation)
    annotation = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Link"),
        NameObject("/Rect"): ArrayObject([FloatObject(v) for v in [20, 20, 200, 40]]),
        NameObject("/Border"): ArrayObject([NumberObject(0)] * 3),
        NameObject("/A"): DictionaryObject({NameObject("/S"): NameObject("/URI"),
                                             NameObject("/URI"): TextStringObject("https://www.cambridgeinternational.org/")}),
    })
    page[NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
    buffer = BytesIO()
    writer.write(buffer)
    writer.close()
    return buffer.getvalue()


class Response:
    status_code = 200

    def __init__(self, data: bytes, event: threading.Event | None = None):
        self.data = data
        self.headers = {"Content-Length": str(len(data))}
        self.event = event

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def iter_content(self, chunk_size: int):
        if self.event:
            yield self.data[:16]
            self.event.set()
            yield self.data[16:]
        else:
            yield self.data


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def get(self, *args, **kwargs):
        return next(self.responses)


def paper(kind: str) -> Paper:
    filename = f"0580_s24_{kind}_21.pdf"
    return Paper(code="0580", year=2024, session="s", kind=kind, component="21",
                 filename=filename, source="PapaCambridge",
                 url=f"https://pastpapers.papacambridge.com/directories/CAIE/{filename}")


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.output = self.folder / "combined.pdf"
        self.cancel = threading.Event()

    def test_original_text_orientation_and_link_annotations_survive(self):
        responses = [Response(text_pdf("FIRST QUESTION PAPER", 842, 595)),
                     Response(text_pdf("SECOND MARK SCHEME", 595, 842, 90))]
        with patch("papermerge.engine.requests.Session", return_value=Session(responses)):
            result = build_pdf([paper("qp"), paper("ms")], self.output, self.cancel, lambda *_: None)
        self.assertEqual(result.page_count, 2)
        reader = PdfReader(self.output)
        self.addCleanup(reader.close)
        self.assertEqual([p.extract_text().strip() for p in reader.pages],
                         ["FIRST QUESTION PAPER", "SECOND MARK SCHEME"])
        self.assertEqual([(int(p.mediabox.width), int(p.mediabox.height), p.rotation)
                          for p in reader.pages], [(842, 595, 0), (595, 842, 90)])
        self.assertEqual([p["/Annots"][0].get_object()["/A"]["/URI"] for p in reader.pages],
                         ["https://www.cambridgeinternational.org/"] * 2)

    def test_cancel_mid_download_preserves_output_and_cleans_partial_files(self):
        self.output.write_bytes(b"existing output")
        response = Response(text_pdf("CANCELLED", 595, 842), event=self.cancel)
        with patch("papermerge.engine.requests.Session", return_value=Session([response])):
            with self.assertRaises(CancelledError):
                build_pdf([paper("qp")], self.output, self.cancel, lambda *_: None)
        self.assertEqual(self.output.read_bytes(), b"existing output")
        self.assertEqual(list(self.folder.iterdir()), [self.output])

    def test_oversized_response_does_not_write_or_replace_destination(self):
        self.output.write_bytes(b"existing output")
        response = Response(b"unread body")
        response.headers["Content-Length"] = str(101 * 1024 * 1024)
        with patch("papermerge.engine.requests.Session", return_value=Session([response])):
            with self.assertRaisesRegex(MergeError, "100 MB"):
                build_pdf([paper("qp")], self.output, self.cancel, lambda *_: None)
        self.assertEqual(self.output.read_bytes(), b"existing output")
        self.assertEqual(list(self.folder.iterdir()), [self.output])


class CatalogAcceptanceTests(unittest.TestCase):
    def test_combined_legacy_components_keep_literal_plus_signs(self):
        url = "https://pastpapers.papacambridge.com/viewer?files=https://pastpapers.papacambridge.com/directories/upload/9709_w03_ms_1+2+3.pdf"
        parsed = parse_paper_link(url, "PapaCambridge", "9709")
        self.assertIsNotNone(parsed)
        self.assertEqual((parsed.year, parsed.component, parsed.filename),
                         (2003, "1+2+3", "9709_w03_ms_1+2+3.pdf"))
        self.assertTrue(parsed.url.endswith("9709_w03_ms_1+2+3.pdf"))

    def test_leading_zero_is_preserved_and_adjacent_syllabus_is_rejected(self):
        self.assertEqual(validate_code(" 0580 "), "0580")
        with self.assertRaises(ValueError):
            validate_code("580")
        parsed = parse_paper_link("https://pastpapers.papacambridge.com/files/0580_s24_qp_21.pdf", "Test", "0580")
        self.assertEqual((parsed.code, parsed.year, parsed.session, parsed.component), ("0580", 2024, "s", "21"))
        self.assertIsNone(parse_paper_link("https://pastpapers.papacambridge.com/files/0581_s24_qp_21.pdf", "Test", "0580"))

    def test_failed_session_cannot_return_an_incomplete_paper_list(self):
        def html(url, cancel):
            if url.endswith("/igcse"):
                return '<a href="papers/caie/igcse-mathematics-0580">Mathematics 0580</a>'
            if url.endswith("/igcse-mathematics-0580"):
                return ('<a href="papers/caie/igcse-mathematics-0580-2024-may-june">2024 May June</a>'
                        '<a href="papers/caie/igcse-mathematics-0580-2024-oct-nov">2024 Oct Nov</a>')
            if url.endswith("2024-may-june"):
                return '<a href="/files/0580_s24_qp_21.pdf">Download</a>'
            raise CatalogError("Simulated missing session listing")
        with patch("papermerge.catalog._get_html", side_effect=html):
            with patch("papermerge.catalog._from_gce", side_effect=CatalogError("Second repository unavailable")):
                with self.assertRaisesRegex(CatalogError, "No partial listing"):
                    discover("0580", "IGCSE", 2024, 2024, {"s", "w"}, {"qp"}, set(), threading.Event(), lambda *_: None)


if __name__ == "__main__":
    unittest.main()
