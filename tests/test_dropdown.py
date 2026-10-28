"""Hidden-widget acceptance checks for syllabus selection and refresh state."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from papermerge.gui import PaperMergeApp
from papermerge.syllabuses import Syllabus


class DropdownTests(unittest.TestCase):
    def setUp(self):
        self.a_level = [
            Syllabus("9700", "Biology", "AS & A Level"),
            Syllabus("9709", "Mathematics", "AS & A Level"),
            Syllabus("9231", "Mathematics - Further", "AS & A Level"),
        ]
        self.igcse = [
            Syllabus("0606", "Additional Mathematics", "IGCSE"),
            Syllabus("0610", "Biology", "IGCSE"),
            Syllabus("0580", "Mathematics", "IGCSE"),
        ]
        self.catalogue = {"AS & A Level": self.a_level, "IGCSE": self.igcse}
        self.bundled_patch = patch("papermerge.gui.load_bundled", side_effect=lambda qualification: list(self.catalogue[qualification]))
        self.bundled_patch.start()
        self.addCleanup(self.bundled_patch.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = PaperMergeApp(self.root, auto_refresh=False)

    def values(self):
        return tuple(self.app.code_entry.cget("values"))

    def test_dropdown_shows_every_subject_with_its_code(self):
        self.assertIsInstance(self.app.code_entry, ttk.Combobox)
        self.assertEqual(set(self.values()), {entry.label for entry in self.a_level})
        self.assertEqual(self.app._syllabus_code(), "9709")

    def test_qualification_switch_replaces_list_and_incompatible_selection(self):
        self.app.qualification.set("IGCSE")
        self.assertEqual(set(self.values()), {entry.label for entry in self.igcse})
        self.assertEqual(self.app._syllabus_code(), "0580")
        self.assertNotIn("9709", self.app.code.get())
        self.app.qualification.set("AS & A Level")
        self.assertEqual(self.app._syllabus_code(), "9709")

    def test_search_matches_subject_or_code_and_empty_restores_all(self):
        self.app.code.set("BIO")
        self.assertEqual(self.values(), (self.a_level[0].label,))
        self.assertEqual(self.app.code.get(), "BIO")
        self.app.code.set("9709")
        self.assertEqual(self.values(), (self.a_level[1].label,))
        self.app.code.set("")
        self.assertEqual(set(self.values()), {entry.label for entry in self.a_level})

    def test_leading_zero_is_preserved_when_selected_or_typed(self):
        self.app.qualification.set("IGCSE")
        self.app.code.set("0580")
        self.assertEqual(self.app._read_filters()["code"], "0580")
        self.app.code.set(self.igcse[2].label)
        self.assertEqual(self.app._read_filters()["code"], "0580")

    def test_unselected_subject_query_and_unknown_code_are_rejected(self):
        for invalid in ("Biology", "97", "9999", "9709 forged label"):
            self.app.code.set(invalid)
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.app._read_filters()

    def test_busy_state_restores_searchable_syllabus_and_readonly_qualification(self):
        self.app._set_busy(True)
        self.assertEqual(str(self.app.code_entry.cget("state")), "disabled")
        self.app._set_busy(False)
        self.assertEqual(str(self.app.code_entry.cget("state")), "normal")
        qualification = next(control for control in self.app.input_controls
                             if isinstance(control, ttk.Combobox) and control is not self.app.code_entry)
        self.assertEqual(str(qualification.cget("state")), "readonly")

    def test_live_refresh_preserves_active_search_and_download_status(self):
        self.app.code.set("Biol")
        self.app.status.set("Downloading selected papers...")
        entries = self.a_level + [Syllabus("9999", "Test subject", "AS & A Level")]
        self.app._apply_syllabus_reply(self.app.syllabus_generation, "AS & A Level", entries)
        self.assertEqual(self.app.code.get(), "Biol")
        self.assertEqual(self.values(), (self.a_level[0].label,))
        self.assertEqual(self.app.status.get(), "Downloading selected papers...")

    def test_stale_or_wrong_qualification_reply_does_not_replace_current_list(self):
        before = tuple(self.app.syllabuses)
        self.app._apply_syllabus_reply(self.app.syllabus_generation - 1, "AS & A Level", self.igcse)
        self.assertEqual(tuple(self.app.syllabuses), before)
        self.app._apply_syllabus_reply(self.app.syllabus_generation, "IGCSE", self.igcse)
        self.assertEqual(tuple(self.app.syllabuses), before)

    def test_live_rename_keeps_selected_syllabus_by_code(self):
        self.app.code.set(self.a_level[1].label)
        renamed = [Syllabus("9709", "Mathematics (updated name)", "AS & A Level")]
        self.app._apply_syllabus_reply(self.app.syllabus_generation, "AS & A Level", renamed)
        self.assertEqual(self.app._syllabus_code(), "9709")
        self.assertEqual(self.app.code.get(), renamed[0].label)


if __name__ == "__main__":
    unittest.main()
