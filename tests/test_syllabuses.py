import threading
import unittest
from unittest.mock import patch

from papermerge.catalog import CatalogError, Cancelled
from papermerge.syllabuses import (Syllabus, list_syllabuses, load_bundled,
    parse_gce_syllabuses, parse_papa_syllabuses)


class SyllabusTests(unittest.TestCase):
    def test_papa_leading_zeros_titles_and_deduplication(self):
        html = '''<a href="papers/caie/igcse-mathematics-0580">Mathematics - 0580</a>
        <a href="/papers/caie/igcse-mathematics-0580">0580</a>
        <a href="papers/caie/igcse-english-0990">English - 0990</a>
        <a href="papers/caie/igcse-business-studies-0986-uk">Business-Studies-0986-UK</a>'''
        result = parse_papa_syllabuses(html, "IGCSE")
        self.assertEqual({x.code for x in result}, {"0580", "0990", "0986"})
        maths = next(x for x in result if x.code == "0580")
        self.assertEqual(maths.title, "Mathematics")
        self.assertEqual(maths.label, "0580 — Mathematics")
        self.assertEqual(result[0].title, "Business Studies - UK")

    def test_excludes_other_qualification_session_and_external_links(self):
        html = '''<a href="papers/caie/igcse-mathematics-0580">Mathematics - 0580</a>
        <a href="papers/caie/igcse-mathematics-0580-2025-march">2025 March</a>
        <a href="papers/caie/as-and-a-level-mathematics-9709">Maths - 9709</a>
        <a href="https://example.com/papers/caie/igcse-fake-0000">Fake - 0000</a>
        <a href="papers/caie/igcse-fake-00580">Fake - 00580</a>'''
        self.assertEqual([x.code for x in parse_papa_syllabuses(html, "IGCSE")], ["0580"])

    def test_parenthesized_code_is_removed_but_region_retained(self):
        html = '<a href="papers/caie/igcse-french-0685">French - Foreign Language (UK) (0685)</a>'
        result = parse_papa_syllabuses(html, "IGCSE")
        self.assertEqual(result[0].title, "French - Foreign Language (UK)")

    def test_unrecognisable_listing_is_error(self):
        with self.assertRaises(CatalogError):
            parse_papa_syllabuses('<html>Access blocked</html>', "IGCSE")

    def test_gce_parses_real_directory_subject_entries(self):
        html = '''<a href="Mathematics%20(9709)/">Mathematics (9709)/</a>
        <a href="../">Parent Directory</a><a href="2025/">2025/</a>'''
        result = parse_gce_syllabuses(html, "AS & A Level")
        self.assertEqual(result[0], Syllabus("9709", "Mathematics", "AS & A Level"))

    def test_refresh_uses_fallback_and_honours_cancellation(self):
        html = '<a href="Mathematics%20(9709)/">Mathematics (9709)/</a>'
        with patch('papermerge.syllabuses._get_html', side_effect=[CatalogError('Unavailable'), html]):
            result = list_syllabuses("AS & A Level", threading.Event(), lambda _: None)
        self.assertEqual(result[0].code, "9709")
        event = threading.Event()
        event.set()
        with patch('papermerge.syllabuses._get_html') as fetch:
            with self.assertRaises(Cancelled):
                list_syllabuses("IGCSE", event, lambda _: None)
            fetch.assert_not_called()

    def test_bundled_snapshot_contains_both_qualifications(self):
        for qualification, expected in [('IGCSE', '0580'), ('AS & A Level', '9709')]:
            result = load_bundled(qualification)
            self.assertGreater(len(result), 50)
            self.assertIn(expected, [item.code for item in result])
            self.assertEqual(len(result), len({item.code for item in result}))


if __name__ == '__main__':
    unittest.main()
