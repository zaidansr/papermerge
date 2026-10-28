"""Offline package smoke test, available through --self-test <directory>."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading


def run(directory=None):
    target = Path(directory) if directory else Path(tempfile.mkdtemp(prefix="papermerge-selftest-"))
    target.mkdir(parents=True, exist_ok=True)
    report = {"ok": False}
    try:
        import tkinter as tk
        from pypdf import PdfReader, PdfWriter
        from .catalog import Paper, validate_code
        from . import engine
        from .gui import PaperMergeApp
        root = tk.Tk()
        root.withdraw()
        app = PaperMergeApp(root, auto_refresh=False)
        root.update_idletasks()
        assert len(app.syllabuses) > 50, "Bundled A Level catalogue is missing"
        a_level_count = len(app.syllabuses)
        assert app._read_filters()["code"] == "9709"
        app.qualification.set("IGCSE")
        assert len(app.syllabuses) > 50, "Bundled IGCSE catalogue is missing"
        igcse_count = len(app.syllabuses)
        app.code.set("Biology")
        assert app.code_entry.cget("values"), "Subject search returned no matches"
        app.code.set("0580")
        assert app._read_filters()["code"] == "0580"
        root.destroy()
        assert validate_code("0580") == "0580"
        files = []
        for width in (320, 640):
            writer = PdfWriter()
            writer.add_blank_page(width=width, height=480)
            stream = BytesIO()
            writer.write(stream)
            writer.close()
            files.append(stream.getvalue())
        class Response:
            status_code = 200
            def __init__(self, data):
                self.data = data
                self.headers = {"Content-Length": str(len(data))}
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.close()
            def close(self):
                pass
            def iter_content(self, chunk_size):
                yield self.data
        class Session:
            def __init__(self):
                self.headers = {}
                self.index = 0
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def get(self, *args, **kwargs):
                response = Response(files[self.index])
                self.index += 1
                return response
        papers = [Paper("0580", 2025, "m", kind, "12", f"0580_m25_{kind}_12.pdf", f"https://pastpapers.papacambridge.com/{kind}.pdf", "Self-test") for kind in ("qp", "ms")]
        original = engine.requests.Session
        try:
            engine.requests.Session = Session
            result = engine.build_pdf(papers, target / "smoke.pdf", threading.Event(), lambda *args: None)
        finally:
            engine.requests.Session = original
        with PdfReader(result.path) as reader:
            assert [float(p.mediabox.width) for p in reader.pages] == [320.0, 640.0]
            assert [x.title for x in reader.outline] == [p.filename for p in papers]
        report = {"ok": True, "gui": "Searchable syllabus dropdown and qualification switching verified", "syllabuses": {"IGCSE": igcse_count, "AS & A Level": a_level_count}, "merge": "2 files, 2 pages, page order and bookmarks verified", "paper_count": result.paper_count, "page_count": result.page_count}
    except Exception as exc:
        import traceback
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    (target / "self-test.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
