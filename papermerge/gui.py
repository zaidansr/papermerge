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

SESSION_NAMES = {"m": "Feb / Mar", "s": "May / Jun", "w": "Oct / Nov"}
KIND_NAMES = {"qp": "Question papers", "ms": "Mark schemes", "in": "Inserts", "er": "Examiner reports", "gt": "Grade thresholds", "ci": "Instructions"}
SHORT_KINDS = {"qp": "Question paper", "ms": "Mark scheme", "in": "Insert", "er": "Examiner report", "gt": "Grade thresholds", "ci": "Instructions"}


class PaperMergeApp:
    def __init__(self, root: tk.Tk, auto_refresh: bool = True):
        self.root = root
        self.root.title("PaperMerge | Cambridge past papers")
        self.root.geometry("1080x820")
        self.root.minsize(960, 750)
        self.root.configure(bg="#edf2f7")
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
        self._qualification_changed()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(80, self._poll)

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#edf2f7", foreground="#172c43")
        style.configure("Card.TFrame", background="white")
        style.configure("Card.TLabel", background="white")
        style.configure("Muted.TLabel", background="white", foreground="#56677b", font=("Segoe UI", 9))
        style.configure("Card.TCheckbutton", background="white", padding=(0, 4))
        style.map("Card.TCheckbutton", background=[("active", "white")])
        style.configure("TButton", padding=(13, 7))
        style.configure("Accent.TButton", background="#176b87", foreground="white", font=("Segoe UI Semibold", 10), padding=(18, 9))
        style.map("Accent.TButton", background=[("disabled", "#b6c6ce"), ("active", "#0e536b")], foreground=[("disabled", "#f4f7f9")])
        style.configure("Treeview", background="white", fieldbackground="white", rowheight=29, borderwidth=0)
        style.configure("Treeview.Heading", background="#e7edf4", font=("Segoe UI Semibold", 9), padding=(6, 7))
        style.map("Treeview", background=[("selected", "#daeaf2")], foreground=[("selected", "#172c43")])
        style.configure("Horizontal.TProgressbar", background="#176b87", troughcolor="#dce5ed", borderwidth=0, thickness=6)

    def _input(self, control):
        self.input_controls.append(control)
        return control

    def _layout(self):
        header = tk.Frame(self.root, bg="#122a42", padx=25, pady=19)
        header.pack(fill="x")
        tk.Label(header, text="PaperMerge", font=("Segoe UI Semibold", 25), bg="#122a42", fg="white").pack(anchor="w")
        tk.Label(header, text="Cambridge IGCSE & AS / A Level  •  Find. Select. Merge.", font=("Segoe UI", 11), bg="#122a42", fg="#bbcfdf").pack(anchor="w", pady=(3, 0))
        body = ttk.Frame(self.root, padding=(22, 17, 22, 14))
        body.pack(fill="both", expand=True)
        card = ttk.Frame(body, style="Card.TFrame", padding=17)
        card.pack(fill="x")
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x")
        labels = ["Qualification", "Syllabus — search by code or subject name"]
        for col, label in enumerate(labels):
            ttk.Label(row, text=label, style="Card.TLabel").grid(row=0, column=col, sticky="w", padx=(0, 16), pady=(0, 5))
        self._input(ttk.Combobox(row, textvariable=self.qualification, values=("AS & A Level", "IGCSE"), state="readonly", width=19)).grid(row=1, column=0, sticky="ew", padx=(0, 16))
        self.code_entry = self._input(ttk.Combobox(row, textvariable=self.code, width=48, height=18, state="normal", postcommand=self._filter_syllabus_choices))
        self.code_entry.grid(row=1, column=1, sticky="ew")
        row.columnconfigure(1, weight=1)
        catalogue_row = ttk.Frame(card, style="Card.TFrame")
        catalogue_row.pack(fill="x", pady=(5, 9))
        ttk.Label(catalogue_row, textvariable=self.syllabus_status, style="Muted.TLabel").pack(side="left")
        self.refresh_button = ttk.Button(catalogue_row, text="Refresh list", command=self._refresh_syllabuses)
        self.refresh_button.pack(side="right")
        details = ttk.Frame(card, style="Card.TFrame")
        details.pack(fill="x")
        for col, label in enumerate(("From year", "To year", "Components (optional)")):
            ttk.Label(details, text=label, style="Card.TLabel").grid(row=0, column=col, sticky="w", padx=(0, 16), pady=(0, 5))
        for col, var in [(0, self.start_year), (1, self.end_year)]:
            self._input(ttk.Spinbox(details, textvariable=var, from_=1980, to=date.today().year, width=10)).grid(row=1, column=col, sticky="ew", padx=(0, 16))
        self._input(ttk.Entry(details, textvariable=self.components, width=24)).grid(row=1, column=2, sticky="ew")
        ttk.Label(details, text="2 = paper 2 variants; 21,22 = exact variants; blank = all.", style="Muted.TLabel").grid(row=1, column=3, sticky="w", padx=(16, 0))
        details.columnconfigure(3, weight=1)
        sessions = ttk.Frame(card, style="Card.TFrame")
        sessions.pack(fill="x", pady=(9, 0))
        ttk.Label(sessions, text="Sessions", style="Card.TLabel", width=10).pack(side="left")
        for key, label in SESSION_NAMES.items():
            self._input(ttk.Checkbutton(sessions, text=label, variable=self.sessions[key], style="Card.TCheckbutton")).pack(side="left", padx=(0, 20))
        kinds = ttk.Frame(card, style="Card.TFrame")
        kinds.pack(fill="x", pady=(3, 0))
        ttk.Label(kinds, text="Include", style="Card.TLabel", width=10).grid(row=0, column=0, sticky="w")
        for i, (key, label) in enumerate(KIND_NAMES.items()):
            self._input(ttk.Checkbutton(kinds, text=label, variable=self.kinds[key], style="Card.TCheckbutton")).grid(row=i // 3, column=1 + i % 3, sticky="w", padx=(0, 20))
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(13, 10))
        self.find_button = ttk.Button(actions, text="Find papers", style="Accent.TButton", command=self._find)
        self.find_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=9)
        ttk.Label(actions, textvariable=self.count, font=("Segoe UI Semibold", 10)).pack(side="right")
        table_frame = ttk.Frame(body)
        table_frame.pack(fill="both", expand=True)
        columns = ("use", "filename", "year", "session", "kind", "component", "source")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse", height=9)
        for col, label, width in [("use", "Use", 42), ("filename", "File (merge order)", 240), ("year", "Year", 55), ("session", "Session", 90), ("kind", "Type", 128), ("component", "Component", 82), ("source", "Source", 130)]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, minwidth=width if col != "filename" else 160, stretch=col in ("filename", "source"), anchor="w" if col in ("filename", "kind", "source") else "center")
        vscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Button-1>", self._table_click)
        self.tree.bind("<space>", self._table_space)
        choices = ttk.Frame(body)
        choices.pack(fill="x", pady=(7, 10))
        self.all_button = ttk.Button(choices, text="Select all", command=lambda: self._select_all(True), state="disabled")
        self.all_button.pack(side="left")
        self.none_button = ttk.Button(choices, text="Select none", command=lambda: self._select_all(False), state="disabled")
        self.none_button.pack(side="left", padx=7)
        ttk.Label(choices, text="Click a row or press Space to include / exclude a file.", foreground="#56677b", font=("Segoe UI", 9)).pack(side="left", padx=6)
        self.merge_button = ttk.Button(choices, text="Download & merge PDF…", style="Accent.TButton", command=self._merge, state="disabled")
        self.merge_button.pack(side="right")
        self.progress = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        ttk.Label(body, textvariable=self.status, wraplength=980, font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 4))
        self.log = tk.Text(body, height=3, font=("Consolas", 9), bg="#e5ecf3", fg="#41566e", borderwidth=0, padx=9, pady=6, state="disabled", wrap="word")
        self.log.pack(fill="x")
        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(9, 0))
        ttk.Label(footer, text="Public repositories • Availability varies by subject and year • Independent app, unaffiliated with Cambridge", font=("Segoe UI", 8), foreground="#64758a").pack(side="left")
        self.open_button = ttk.Button(footer, text="Open PDF", command=self._open, state="disabled")
        self.open_button.pack(side="right")

    def _filters_changed(self, *_):
        if self.papers and not self.busy:
            self.papers = []
            self.checked.clear()
            self.tree.delete(*self.tree.get_children())
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
        labels = [subject.label for subject in self.syllabuses]
        selected = any(label.casefold() == text for label in labels)
        matches = labels if not text or selected else [label for label in labels if text in label.casefold()]
        self.code_entry.configure(values=matches)

    def _install_syllabuses(self, entries, reset_selection=False):
        previous = self.code.get().strip()
        # Only an exact code or an existing complete label counts as a selection.
        selected = next((subject for subject in self.syllabuses if subject.label == previous), None)
        previous_code = selected.code if selected else previous
        self.syllabuses = list(entries)
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
            messagebox.showerror("Check your filters", str(exc), parent=self.root)
            return
        self.papers = []
        self.checked.clear()
        self.tree.delete(*self.tree.get_children())
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
            widget.configure(state="disabled" if busy else ("readonly" if isinstance(widget, ttk.Combobox) and widget is not self.code_entry else "normal"))
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
                    for i, paper in enumerate(value):
                        self.tree.insert("", "end", iid=str(i), values=("[x]", paper.filename, paper.year, SESSION_NAMES.get(paper.session, paper.session), SHORT_KINDS.get(paper.kind, paper.kind), paper.component or "—", paper.source))
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
