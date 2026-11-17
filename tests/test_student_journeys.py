"""First-time student mistakes and complete selection journeys, using offline fixtures."""
import threading
import tkinter as tk
import unittest
from unittest.mock import patch
from papermerge.gui import PaperMergeApp
from papermerge.catalog import Paper
from papermerge.presets import TOP_SUBJECTS, SESSION_PRESETS, TYPE_PRESETS
from papermerge.syllabuses import load_bundled


class StudentJourneys(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = PaperMergeApp(self.root, auto_refresh=False)
        self.addCleanup(self.root.destroy)

    def test_both_top_twenty_collections_are_complete_and_unique(self):
        for qualification in TOP_SUBJECTS:
            self.app.qualification.set(qualification)
            self.app.subject_scope.set('Top 20 subjects')
            self.app.code.set('')
            values = self.app.code_entry.cget('values')
            self.assertEqual(len(values), 20)
            self.assertEqual(len(set(values)), 20)
            self.assertTrue(set(TOP_SUBJECTS[qualification]) <= {s.code for s in load_bundled(qualification)})

    def test_every_curated_subject_can_be_selected_and_validated(self):
        for qualification, codes in TOP_SUBJECTS.items():
            self.app.qualification.set(qualification)
            for code in codes:
                self.app.code.set(code)
                self.assertEqual(self.app._read_filters()['code'], code)

    def test_subject_scope_does_not_hide_collection_behind_previous_selection(self):
        self.app.code.set(next(s.label for s in self.app.syllabuses if s.code == '8680'))
        self.app.subject_scope.set('Top 20 subjects')
        self.assertEqual(len(self.app.code_entry.cget('values')), 20)

    def test_each_session_and_document_dropdown_maps_to_actual_filters(self):
        for label, expected in SESSION_PRESETS.items():
            self.app.session_choice.set(label)
            self.assertEqual(self.app._read_filters()['sessions'], expected)
        for label, expected in TYPE_PRESETS.items():
            self.app.type_choice.set(label)
            self.assertEqual(self.app._read_filters()['kinds'], expected)

    def test_paper_dropdown_and_exact_variant_entry(self):
        for text, expected in [('All papers', set()), ('Paper 2 — all variants', {'2'}), ('21,22', {'21','22'}), ('', set())]:
            self.app.components.set(text)
            self.assertEqual(self.app._read_filters()['components'], expected)

    def test_mistyped_filters_are_explained_inline_without_network(self):
        for field, value in [(self.app.code, ''), (self.app.code, '580'), (self.app.start_year,'banana'), (self.app.start_year,'9999'), (self.app.components,'paper banana')]:
            original = field.get()
            field.set(value)
            with patch.object(self.app, '_launch') as launch:
                self.app._find()
                launch.assert_not_called()
                self.assertTrue(self.app.validation.get())
            field.set(original)

    def test_reversed_years_and_empty_required_selections(self):
        self.app.start_year.set('2025')
        self.app.end_year.set('2024')
        with self.assertRaises(ValueError): self.app._read_filters()
        self.app.end_year.set('2026')
        for var in self.app.sessions.values(): var.set(False)
        with self.assertRaises(ValueError): self.app._read_filters()

    def fixture_papers(self):
        self.app.papers = [Paper('9709',2025,'m',kind,'12',f'9709_m25_{kind}_12.pdf','https://pastpapers.papacambridge.com/test.pdf','Fixture') for kind in ('qp','ms')]
        self.app.checked = {0,1}
        self.app._render_results()
        self.app._update_selection()

    def test_results_search_keeps_selection_and_does_not_duplicate_rows(self):
        self.fixture_papers()
        self.app._toggle('1')
        self.app.result_query.set('mark scheme')
        self.assertEqual(self.app.tree.get_children(), ('1',))
        self.assertEqual(self.app.checked, {0})
        self.app.result_query.set('')
        self.assertEqual(self.app.tree.get_children(), ('0','1'))
        self.assertEqual(self.app.tree.set('1','use'), '[ ]')
        self.app.result_query.set('nonsense')
        self.assertIn('Clear search', self.app.empty_text.get())

    def test_filter_change_clears_all_old_results_even_after_search(self):
        self.fixture_papers()
        self.app.result_query.set('qp')
        self.app.start_year.set('2020')
        self.assertEqual(self.app.papers, [])
        self.assertFalse(self.app.tree.exists('1'))
        self.assertEqual(str(self.app.merge_button.cget('state')), 'disabled')

    def test_cancelled_save_dialog_does_not_download_anything(self):
        self.fixture_papers()
        with patch('papermerge.gui.filedialog.asksaveasfilename', return_value=''), patch.object(self.app,'_launch') as launch:
            self.app._merge()
            launch.assert_not_called()

    def test_busy_state_protects_selection_and_restores_year_search(self):
        self.fixture_papers()
        self.app._set_busy(True)
        self.app._toggle('0')
        self.assertEqual(self.app.checked,{0,1})
        self.app._set_busy(False)
        self.assertEqual(str(self.app.component_entry.cget('state')), 'normal')

if __name__ == '__main__': unittest.main()
