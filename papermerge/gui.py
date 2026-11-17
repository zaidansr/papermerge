"""Responsive Tk desktop interface. Workers communicate only through a queue."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import os
import queue
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .catalog import discover, validate_code
from .engine import build_pdf, CancelledError
from .syllabuses import Syllabus, list_syllabuses, load_bundled
from .presets import TOP_SUBJECTS, SUBJECT_HINTS, SESSION_PRESETS, TYPE_PRESETS

SESSION_NAMES = {"m": "Feb / Mar", "s": "May / Jun", "w": "Oct / Nov"}
KIND_NAMES = {"qp": "Question papers", "ms": "Mark schemes", "in": "Inserts", "er": "Examiner reports", "gt": "Grade thresholds", "ci": "Instructions"}
SHORT_KINDS = {"qp": "Question paper", "ms": "Mark scheme", "in": "Insert", "er": "Examiner report", "gt": "Grade thresholds", "ci": "Instructions"}


class PaperMergeApp:
    def __init__(self, root: tk.Tk, auto_refresh: bool = True):
        self.root = root
        self.root.title("PaperMerge | Cambridge past papers")
        self.root.geometry("1120x900")
        self.root.minsize(900, 760)
        self.root.configure(bg="#f5f5f7")
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets" / "papermerge.ico"
        if icon.is_file():
            try:
                self.root.iconbitmap(str(icon))
            except tk.TclError:
                pass
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.closing = False
        self.papers = []
        self.checked: set[int] = set()
        self.last_output: Path | None = None
        self.busy = False
        self.input_controls = []
        self.subject_scope = tk.StringVar(value="All subjects")
        self.session_choice = tk.StringVar(value="All sessions")
        self.type_choice = tk.StringVar(value="Question papers")
        self.result_query = tk.StringVar()
        self._row_ids = set()
        self.validation = tk.StringVar()
        self.empty_text = tk.StringVar(value="Your papers will appear here.\nChoose a subject, then select Find papers.")
        self.auto_refresh = auto_refresh
        self.syllabuses: list[Syllabus] = []
        self.syllabus_generation = 0
        self.syllabus_cancel = threading.Event()
        self.syllabus_status = tk.StringVar(value="Loading syllabus list…")
        self.code = tk.StringVar(value="9709")
        self.qualification = tk.StringVar(value="AS & A Level")
        self.start_year = tk.StringVar(value=str(date.today().year - 2))
        self.end_year = tk.StringVar(value=str(date.today().year))
        self.components = tk.StringVar()
        self.sessions = {key: tk.BooleanVar(value=True) for key in SESSION_NAMES}
        self.kinds = {key: tk.BooleanVar(value=(key == "qp")) for key in KIND_NAMES}
        self.status = tk.StringVar(value="Choose a syllabus and filters, then find papers.")
        self.count = tk.StringVar(value="No papers loaded")
        self._style()
        self._layout()
        for var in [self.code, self.qualification, self.start_year, self.end_year, self.components, *self.sessions.values(), *self.kinds.values()]:
            var.trace_add("write", self._filters_changed)
        self.code.trace_add("write", self._filter_syllabus_choices)
        self.qualification.trace_add("write", self._qualification_changed)
        self.subject_scope.trace_add("write", self._filter_syllabus_choices)
        self.session_choice.trace_add("write", self._preset_changed)
        self.type_choice.trace_add("write", self._preset_changed)
        self.result_query.trace_add("write", self._render_results)
        self._qualification_changed()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(80, self._poll)

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 11), background="#f5f5f7", foreground="#161616")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Card.TLabel", background="#ffffff")
        style.configure("Muted.TLabel", background="#ffffff", foreground="#595959", font=("Segoe UI", 10))
        style.configure("TButton", padding=(14, 10), background="#ededed", borderwidth=0)
        style.configure("Quiet.TButton", padding=(10, 4), font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#dddddd")], foreground=[("disabled", "#757575")])
        style.configure("Accent.TButton", background="#161616", foreground="#ffffff", font=("Segoe UI Semibold", 11), padding=(22, 12))
        style.map("Accent.TButton", background=[("disabled", "#d4d4d4"), ("active", "#383838")], foreground=[("disabled", "#626262")])
        style.configure("TCombobox", padding=(10, 8), fieldbackground="#ffffff", selectbackground="#161616", selectforeground="#ffffff", arrowsize=16)
        style.configure("TEntry", padding=(10, 8), fieldbackground="#ffffff")
        style.map("TCombobox", fieldbackground=[("readonly", "#ffffff")], foreground=[("readonly", "#161616")])
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", rowheight=36, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#eeeeee", font=("Segoe UI Semibold", 10), padding=(8, 10))
        style.map("Treeview", background=[("selected", "#e3e3e3")], foreground=[("selected", "#111111")])
        style.configure("Horizontal.TProgressbar", background="#161616", troughcolor="#e3e3e3", borderwidth=0, thickness=5)
        self.root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 11))
        self.root.option_add("*TCombobox*Listbox.background", "white")
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#161616")
        self.root.option_add("*TCombobox*Listbox.selectForeground", "white")

    def _input(self, control):
        self.input_controls.append(control)
        return control

    def _combo(self, parent, variable, values, width=18, editable=False):
        widget = self._input(ttk.Combobox(parent, textvariable=variable, values=values, width=width, height=12, state="normal" if editable else "readonly"))
        widget.searchable = editable
        original = tuple(values)
        if editable:
            def filter_options(_event=None):
                query = variable.get().strip().casefold()
                widget.configure(values=original if not query or variable.get() in original else [v for v in original if query in str(v).casefold()])
            widget.bind("<KeyRelease>", filter_options)
            widget.configure(postcommand=filter_options)
        return widget

    def _layout(self):
        header = ttk.Frame(self.root, padding=(24, 12, 24, 12))
        header.pack(fill="x")
        ttk.Label(header, text="PaperMerge", font=("Segoe UI Semibold", 22)).pack(side="left")
        ttk.Label(header, text="Your next revision pack, in one PDF.", foreground="#595959").pack(side="left", padx=20)
        body = ttk.Frame(self.root, padding=(28, 0, 28, 18))
        body.pack(fill="both", expand=True)
        card = ttk.Frame(body, style="Card.TFrame", padding=16)
        card.pack(fill="x")
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x")
        for col, label in enumerate(("Qualification", "Subject collection", "Subject name or syllabus code")):
            ttk.Label(row, text=label, style="Card.TLabel").grid(row=0, column=col, sticky="w", pady=(0, 5))
        self._combo(row, self.qualification, ("AS & A Level", "IGCSE"), 17).grid(row=1, column=0, sticky="ew", padx=(0, 12))
        self._combo(row, self.subject_scope, ("All subjects", "Top 20 subjects"), 17).grid(row=1, column=1, sticky="ew", padx=(0, 12))
        self.code_entry = self._input(ttk.Combobox(row, textvariable=self.code, width=34, height=15, state="normal", postcommand=self._filter_syllabus_choices))
        self.code_entry.searchable = True
        self.code_entry.grid(row=1, column=2, sticky="ew")
        row.columnconfigure(2, weight=1)
        catalogue = ttk.Frame(card, style="Card.TFrame")
        catalogue.pack(fill="x", pady=(6, 12))
        ttk.Label(catalogue, textvariable=self.syllabus_status, style="Muted.TLabel").pack(side="left")
        self.refresh_button = ttk.Button(catalogue, text="Refresh subjects", style="Quiet.TButton", command=self._refresh_syllabuses)
        self.refresh_button.pack(side="right")
        details = ttk.Frame(card, style="Card.TFrame")
        details.pack(fill="x")
        specs = (("From year", self.start_year, [str(y) for y in range(date.today().year, 1979, -1)], 8, True),
                 ("To year", self.end_year, [str(y) for y in range(date.today().year, 1979, -1)], 8, True),
                 ("Exam session", self.session_choice, tuple(SESSION_PRESETS), 18, False),
                 ("Include", self.type_choice, tuple(TYPE_PRESETS), 23, False))
        for col, (label, var, choices, width, editable) in enumerate(specs):
            ttk.Label(details, text=label, style="Card.TLabel").grid(row=0, column=col, sticky="w", pady=(0, 5))
            self._combo(details, var, choices, width, editable).grid(row=1, column=col, sticky="ew", padx=(0, 12 if col < 3 else 0))
            details.columnconfigure(col, weight=1)
        paper_row = ttk.Frame(card, style="Card.TFrame")
        paper_row.pack(fill="x", pady=(12, 0))
        ttk.Label(paper_row, text="Paper / variant", style="Card.TLabel").pack(side="left", padx=(0, 12))
        self.component_entry = self._combo(paper_row, self.components, ("", "All papers", *[f"Paper {i} — all variants" for i in range(1, 10)]), 26, True)
        self.component_entry.pack(side="left")
        ttk.Label(paper_row, text="Leave blank for all. Or type exact variants, e.g. 21,22.", style="Muted.TLabel", wraplength=350).pack(side="left", padx=14)
        ttk.Label(body, textvariable=self.validation, foreground="#161616", wraplength=980).pack(anchor="w", pady=(7, 0))
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(8, 12))
        self.find_button = ttk.Button(actions, text="Find papers", style="Accent.TButton", command=self._find)
        self.find_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=10)
        ttk.Label(actions, textvariable=self.count).pack(side="right")
        search = ttk.Frame(body)
        search.pack(fill="x", pady=(0, 8))
        ttk.Label(search, text="Search results", font=("Segoe UI Semibold", 12)).pack(side="left", padx=(0, 12))
        ttk.Entry(search, textvariable=self.result_query, width=34).pack(side="left", fill="x", expand=True)
        ttk.Button(search, text="Clear search", command=lambda: self.result_query.set("")).pack(side="left", padx=(8, 0))
        bottom = ttk.Frame(body)
        bottom.pack(side="bottom", fill="x")
        table_frame = ttk.Frame(body)
        table_frame.pack(fill="both", expand=True)
        columns = ("use", "filename", "year", "session", "kind", "component", "source")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse", height=6, displaycolumns=("use", "filename", "year", "session", "kind", "component"))
        for col, label, width in (("use", "Use", 46), ("filename", "Paper file", 240), ("year", "Year", 55), ("session", "Session", 95), ("kind", "Document", 130), ("component", "Variant", 65), ("source", "Source", 100)):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, minwidth=40, stretch=col == "filename", anchor="w" if col in ("filename", "kind", "source") else "center")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.empty_label = ttk.Label(table_frame, textvariable=self.empty_text, justify="center", anchor="center", background="white", foreground="#595959")
        self.empty_label.place(relx=.5, rely=.55, anchor="center")
        self.tree.bind("<Button-1>", self._table_click)
        self.tree.bind("<space>", self._table_space)
        choices = ttk.Frame(bottom)
        choices.pack(fill="x", pady=(12, 10))
        self.all_button = ttk.Button(choices, text="Select all papers", command=lambda: self._select_all(True), state="disabled")
        self.all_button.pack(side="left")
        self.none_button = ttk.Button(choices, text="Select none", command=lambda: self._select_all(False), state="disabled")
        self.none_button.pack(side="left", padx=8)
        self.merge_button = ttk.Button(choices, text="Save merged PDF…", style="Accent.TButton", command=self._merge, state="disabled")
        self.merge_button.pack(side="right")
        self.progress = ttk.Progressbar(bottom, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        ttk.Label(bottom, textvariable=self.status, wraplength=820).pack(anchor="w", pady=(8, 0))
        self.log = tk.Text(bottom, height=2, font=("Segoe UI", 9), bg="#f5f5f7", fg="#595959", borderwidth=0, state="disabled", wrap="word")
        self.open_button = ttk.Button(choices, text="Open saved PDF", command=self._open, state="disabled")
        self.open_button.pack(side="right", padx=8)

    def _preset_changed(self, *_):
        for key, var in self.sessions.items():
            var.set(key in SESSION_PRESETS[self.session_choice.get()])
        for key, var in self.kinds.items():
            var.set(key in TYPE_PRESETS[self.type_choice.get()])

    def _clear_rows(self):
        for row in self._row_ids:
            if self.tree.exists(row):
                self.tree.delete(row)
        self._row_ids.clear()

    def _render_results(self, *_):
        self._clear_rows()
        query = self.result_query.get().strip().casefold()
        for i, paper in enumerate(self.papers):
            values = ("[x]" if i in self.checked else "[ ]", paper.filename, paper.year, SESSION_NAMES.get(paper.session, paper.session), SHORT_KINDS.get(paper.kind, paper.kind), paper.component or "—", paper.source)
            if not query or query in " ".join(map(str, values)).casefold():
                self.tree.insert("", "end", iid=str(i), values=values)
                self._row_ids.add(str(i))
        if self._row_ids:
            self.empty_label.place_forget()
        else:
            self.empty_text.set("No papers match your search. Clear search to see all files." if self.papers else "No papers yet. Choose a subject, then select Find papers.")
            self.empty_label.place(relx=.5, rely=.55, anchor="center")

    def _filters_changed(self, *_):
        if self.papers and not self.busy:
            self.papers = []
            self.checked.clear()
            self._clear_rows()
            self._render_results()
            self._update_selection()
            self.status.set("Filters changed. Find papers again to refresh the list.")

    def _syllabus_code(self):
        text = self.code.get().strip()
        match = next((subject for subject in self.syllabuses if subject.label == text), None)
        code = match.code if match else validate_code(text)
        if self.syllabuses and code not in {subject.code for subject in self.syllabuses}:
            raise ValueError("Choose an available syllabus from the dropdown, or refresh the syllabus list.")
        return code

    def _filter_syllabus_choices(self, *_):
        text = self.code.get().strip().casefold()
        entries = self.syllabuses
        if self.subject_scope.get() == "Top 20 subjects":
            by_code = {subject.code: subject for subject in entries}
            entries = [by_code[code] for code in TOP_SUBJECTS[self.qualification.get()] if code in by_code]
        labels = [subject.label for subject in entries]
        selected = any(subject.label.casefold() == text for subject in self.syllabuses)
        matches = labels if not text or selected else [label for label in labels if text in label.casefold()]
        self.code_entry.configure(values=matches)

    def _install_syllabuses(self, entries, reset_selection=False):
        previous = self.code.get().strip()
        # Only an exact code or an existing complete label counts as a selection.
        selected = next((subject for subject in self.syllabuses if subject.label == previous), None)
        previous_code = selected.code if selected else previous
        self.syllabuses = [Syllabus(item.code, SUBJECT_HINTS.get(item.code, item.title) if item.title in ("Mathematics", "English", "Computer Science") else item.title, item.qualification) for item in entries]
        if reset_selection and self.syllabuses:
            by_code = {subject.code: subject for subject in self.syllabuses}
            default = "0580" if self.qualification.get() == "IGCSE" else "9709"
            chosen = by_code.get(previous_code) or by_code.get(default) or self.syllabuses[0]
            self.code.set(chosen.label)
        elif reset_selection:
            self.code.set("")
        elif selected:
            updated = next((subject for subject in self.syllabuses if subject.code == previous_code), None)
            self.code.set(updated.label if updated else "")
        self._filter_syllabus_choices()

    def _qualification_changed(self, *_):
        self.syllabus_cancel.set()
        self.syllabus_generation += 1
        qualification = self.qualification.get()
        self._install_syllabuses(load_bundled(qualification), reset_selection=True)
        self.syllabus_status.set(f"{len(self.syllabuses)} listed syllabuses · Type a code or subject name to filter")
        if self.auto_refresh:
            self._refresh_syllabuses()

    def _refresh_syllabuses(self):
        if self.closing:
            return
        self.syllabus_cancel.set()
        self.syllabus_cancel = threading.Event()
        cancel = self.syllabus_cancel
        self.syllabus_generation += 1
        generation = self.syllabus_generation
        qualification = self.qualification.get()
        self.syllabus_status.set(f"{len(self.syllabuses)} listed syllabuses · Refreshing catalogue…")
        def fetch():
            try:
                entries = list_syllabuses(qualification, cancel, lambda _text: None)
                self.events.put(("syllabuses", (generation, qualification, entries, None)))
            except Exception as exc:
                self.events.put(("syllabuses", (generation, qualification, None, exc)))
        threading.Thread(target=fetch, name="PaperMerge-syllabuses", daemon=True).start()

    def _apply_syllabus_reply(self, generation, qualification, entries, error=None):
        if self.closing or generation != self.syllabus_generation or qualification != self.qualification.get():
            return
        if error is None:
            self._install_syllabuses(entries)
            self.syllabus_status.set(f"{len(self.syllabuses)} listed syllabuses · Live catalogue · Type to filter")
        elif self.syllabuses:
            self.syllabus_status.set(f"{len(self.syllabuses)} bundled syllabuses · Refresh unavailable; showing saved list")
        else:
            self.syllabus_status.set("Syllabus list unavailable. Check your connection and click Refresh list.")
        if error is not None:
            self._log(f"Syllabus list: {error}")

    def _read_filters(self):
        code = self._syllabus_code()
        try:
            start, end = int(self.start_year.get()), int(self.end_year.get())
        except ValueError:
            raise ValueError("Enter whole, four-digit years.") from None
        if not (1980 <= start <= end <= date.today().year):
            raise ValueError(f"Choose a year range from 1980 to {date.today().year}, with From year no later than To year.")
        sessions = {key for key, var in self.sessions.items() if var.get()}
        kinds = {key for key, var in self.kinds.items() if var.get()}
        if not sessions or not kinds:
            raise ValueError("Select at least one session and one file type.")
        text = self.components.get().strip()
        if text == "All papers":
            text = ""
        if re.fullmatch(r"Paper [1-9] — all variants", text):
            text = text.split()[1]
        components = set(re.split(r"[\s,;]+", text)) if text else set()
        if any(not re.fullmatch(r"[0-9]{1,2}", item) for item in components):
            raise ValueError("Use one- or two-digit components separated by commas, for example 2 or 21,22.")
        return dict(code=code, qualification=self.qualification.get(), start_year=start, end_year=end, sessions=sessions, kinds=kinds, components=components)

    def _launch(self, task, operation):
        self.cancel = threading.Event()
        self._set_busy(True)
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        def work():
            try:
                self.events.put((operation, task()))
            except Exception as exc:
                self.events.put(("error", exc))
            finally:
                self.events.put(("idle", None))
        self.worker = threading.Thread(target=work, name=f"PaperMerge-{operation}", daemon=True)
        self.worker.start()

    def _find(self):
        if self.busy:
            return
        try:
            filters = self._read_filters()
        except ValueError as exc:
            self.validation.set(str(exc))
            self.code_entry.focus_set()
            return
        self.validation.set("")
        self.papers = []
        self.checked.clear()
        self._clear_rows()
        self.result_query.set("")
        self.count.set("Searching…")
        self._log("Finding " + filters["code"] + " · " + filters["qualification"])
        self.status.set("Finding available papers…")
        self._launch(lambda: discover(**filters, cancel=self.cancel, progress=lambda text: self.events.put(("status", text))), "found")

    def _merge(self):
        if self.busy:
            return
        papers = [paper for i, paper in enumerate(self.papers) if i in self.checked]
        if not papers:
            return
        initial = f"{papers[0].code}_{min(p.year for p in papers)}-{max(p.year for p in papers)}_papers.pdf"
        target = filedialog.asksaveasfilename(parent=self.root, title="Save merged papers", defaultextension=".pdf", filetypes=[("PDF document", "*.pdf")], initialfile=initial)
        if not target:
            return
        output = Path(target)
        if output.suffix.lower() != ".pdf":
            messagebox.showerror("Choose a PDF filename", "The filename must end in .pdf.", parent=self.root)
            return
        self.status.set(f"Downloading {len(papers)} selected files…")
        self._launch(lambda: build_pdf(papers, output, self.cancel, lambda text, done, total: self.events.put(("progress", (text, done, total)))), "merged")

    def _set_busy(self, busy):
        self.busy = busy
        for widget in self.input_controls:
            widget.configure(state="disabled" if busy else ("readonly" if isinstance(widget, ttk.Combobox) and not getattr(widget, "searchable", False) else "normal"))
        self.find_button.configure(state="disabled" if busy else "normal")
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self._update_selection()

    def _update_selection(self):
        available = bool(self.papers) and not self.busy
        self.all_button.configure(state="normal" if available else "disabled")
        self.none_button.configure(state="normal" if available else "disabled")
        self.merge_button.configure(state="normal" if available and self.checked else "disabled")
        self.count.set(f"{len(self.checked)} selected / {len(self.papers)} found" if self.papers else "No papers loaded")

    def _toggle(self, row):
        if self.busy or not row:
            return
        i = int(row)
        if i in self.checked:
            self.checked.remove(i)
        else:
            self.checked.add(i)
        self.tree.set(row, "use", "[x]" if i in self.checked else "[ ]")
        self._update_selection()

    def _table_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell":
            self._toggle(self.tree.identify_row(event.y))

    def _table_space(self, _event):
        self._toggle(self.tree.focus())
        return "break"

    def _select_all(self, selected):
        if self.busy:
            return
        self.checked = set(range(len(self.papers))) if selected else set()
        for row in self.tree.get_children():
            self.tree.set(row, "use", "[x]" if selected else "[ ]")
        self._update_selection()

    def _cancel(self):
        self.cancel.set()
        self.cancel_button.configure(state="disabled")
        self.status.set("Cancelling… waiting for the current network operation to finish.")

    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", str(text) + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 300:
            self.log.delete("1.0", "100.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "status":
                    self.status.set(value)
                    self._log(value)
                elif kind == "syllabuses":
                    self._apply_syllabus_reply(*value)
                elif kind == "progress":
                    text, done, total = value
                    self.status.set(text)
                    self._log(text)
                    self.progress.stop()
                    self.progress.configure(mode="determinate", maximum=max(total, 1), value=done)
                elif kind == "found":
                    self.papers = value
                    self.checked = set(range(len(value)))
                    self._render_results()
                    self.status.set(f"Found {len(value)} files. Review the list, then download & merge." if value else "No matching files found. Try a wider year range, another session, or fewer filters.")
                    self._log(self.status.get())
                elif kind == "merged":
                    self.last_output = value.path
                    self.open_button.configure(state="normal")
                    self.status.set(f"Saved {value.paper_count} files · {value.page_count} pages · {value.path}")
                    self._log(self.status.get())
                    self.progress.configure(mode="determinate", maximum=100, value=100)
                    if not self.closing:
                        messagebox.showinfo("PDF saved", f"Merged {value.paper_count} files into {value.page_count} pages.\n\n{value.path}", parent=self.root)
                elif kind == "error":
                    cancelled = self.cancel.is_set() or isinstance(value, CancelledError)
                    text = "Cancelled. No incomplete PDF was saved." if cancelled else str(value) or type(value).__name__
                    self.status.set(text)
                    self._log(text)
                    if not cancelled and not self.closing:
                        messagebox.showerror("Unable to complete", text, parent=self.root)
                elif kind == "idle":
                    self.progress.stop()
                    self._set_busy(False)
                    if self.closing:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _open(self):
        if self.last_output and self.last_output.is_file():
            try:
                os.startfile(self.last_output)
            except OSError as exc:
                messagebox.showerror("Cannot open PDF", str(exc), parent=self.root)

    def _close(self):
        self.syllabus_cancel.set()
        if self.busy:
            self.closing = True
            self._cancel()
            self.root.withdraw()
        else:
            self.root.destroy()


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    PaperMergeApp(root)
    root.mainloop()
