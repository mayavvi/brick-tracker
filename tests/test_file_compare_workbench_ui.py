from __future__ import annotations

import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FileCompareWorkbenchUiTests(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_page_uses_three_row_layout(self) -> None:
        """Top: horizontal Scope, middle: P/Q cards, bottom: code reader."""
        template = self.read("templates/file_compare.html")

        self.assertIn("file-compare-v2", template)
        self.assertIn("程序范围 Scope", template)
        self.assertIn("横向 Scope", template)
        # P/Q lives as two side-by-side cards, not a single "compare basket".
        self.assertNotIn("比较篮", template)
        self.assertNotIn("file-compare-tray-panel", template)
        self.assertNotIn("file-compare-workbench-grid", template)

    def test_scope_includes_category_filter(self) -> None:
        template = self.read("templates/file_compare.html")
        script = self.read("static/js/file_compare_workbench.js")

        self.assertIn("Category", template)
        self.assertIn('<option value="SDTM">SDTM</option>', template)
        self.assertIn('<option value="ADAM">ADaM</option>', template)
        self.assertIn('<option value="TFL">TFL</option>', template)
        self.assertIn("filters.category", script)
        self.assertIn("category: ''", script)
        self.assertIn("'category'", script)

    def test_qc_panel_groups_by_category(self) -> None:
        template = self.read("templates/file_compare.html")
        script = self.read("static/js/file_compare_workbench.js")

        self.assertIn("QC 状态", template)
        self.assertIn("qcGroupedRows()", template)
        self.assertIn("qcGroupedRows()", script)

    def test_code_reader_is_modal(self) -> None:
        template = self.read("templates/file_compare.html")
        script = self.read("static/js/file_compare_workbench.js")

        self.assertIn('x-show="readerOpen"', template)
        self.assertIn("closeReader()", template)
        self.assertIn("readerOpen:", script)
        self.assertIn("closeReader()", script)

    def test_compare_targets_survive_program_and_filter_changes(self) -> None:
        script = self.read("static/js/file_compare_workbench.js")
        select_program = self._method_body(script, "async selectProgram", "async selectVersion")
        load_programs = self._method_body(script, "async loadPrograms", "async rebuildIndex")

        self.assertNotIn("this.compareP = null", select_program)
        self.assertNotIn("this.compareQ = null", select_program)
        self.assertNotIn("this.diffResult = null", select_program)
        self.assertNotIn("this.clearSelection()", load_programs)
        self.assertIn("clearCompareSlot(slot)", script)
        self.assertIn("clearCompareTray()", script)

    def _method_body(self, source: str, start: str, end: str) -> str:
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
        match = pattern.search(source)
        self.assertIsNotNone(match, f"Missing method range {start} -> {end}")
        assert match is not None
        return match.group(0)


if __name__ == "__main__":
    unittest.main()
