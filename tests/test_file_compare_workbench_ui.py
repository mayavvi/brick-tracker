from __future__ import annotations

import re
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FileCompareWorkbenchUiTests(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_page_uses_three_column_workbench_shell(self) -> None:
        template = self.read("templates/file_compare.html")

        self.assertIn("file-compare-workbench", template)
        self.assertIn("file-compare-workbench-grid", template)
        self.assertIn("file-compare-scope-panel", template)
        self.assertIn("file-compare-reader-panel", template)
        self.assertIn("file-compare-tray-panel", template)
        self.assertIn("比较篮 P/Q", template)
        self.assertNotIn("grid-cols-1 xl:grid-cols-[20rem_minmax(0,1fr)_21rem]", template)

    def test_workbench_side_panels_collapse_to_persistent_rails(self) -> None:
        template = self.read("templates/file_compare.html")
        script = self.read("static/js/file_compare_workbench.js")
        css = self.read("static/css/style.css")

        self.assertIn("scopeCollapsed: false", script)
        self.assertIn("trayCollapsed: false", script)
        self.assertIn("toggleScopePanel()", script)
        self.assertIn("toggleTrayPanel()", script)
        self.assertIn("workbenchLayoutClass()", script)
        self.assertIn("is-scope-collapsed", template)
        self.assertIn("is-tray-collapsed", template)
        self.assertIn("file-compare-panel-rail", template)
        self.assertIn(".file-compare-workbench-grid", css)
        self.assertIn("grid-template-columns: 20rem minmax(22rem, 1fr) 21rem", css)
        self.assertIn(".file-compare-workbench-grid.is-scope-collapsed", css)
        self.assertIn(".file-compare-workbench-grid.is-tray-collapsed", css)
        self.assertIn("2.75rem", css)

    def test_file_compare_copy_is_consistent_and_compact(self) -> None:
        template = self.read("templates/file_compare.html")

        self.assertIn("选择程序查看版本与差异", template)
        self.assertIn("左侧限定范围，中间阅读/比较，右侧固定 P/Q 与 QC。", template)
        self.assertIn("程序范围 Scope", template)
        self.assertIn("版本浏览 Versions", template)
        self.assertIn("比较设置 Diff", template)
        self.assertIn("快照 Snapshots", template)
        self.assertIn("QC 状态", template)
        self.assertNotIn("按程序回看版本与比较结果", template)
        self.assertNotIn("<p class=\"text-[11px] uppercase tracking-[0.18em] text-stone-400\">Scope</p>", template)

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

    def test_snapshot_action_lives_in_reader_toolbar_without_bottom_drawer(self) -> None:
        template = self.read("templates/file_compare.html")
        script = self.read("static/js/file_compare_workbench.js")

        toolbar = self._tag_block(template, "file-compare-reader-toolbar")
        self.assertIn("@click=\"takeSnapshot()\"", toolbar)
        self.assertNotIn("snapshotPanelOpen = !snapshotPanelOpen", template)
        self.assertNotIn("snapshotPanelOpen", script)
        self.assertNotIn("max-h-56 overflow-auto divide-y divide-stone-200", template)

    def test_qc_is_a_compact_tray_panel_not_a_second_full_table(self) -> None:
        template = self.read("templates/file_compare.html")
        script = self.read("static/js/file_compare_workbench.js")

        self.assertIn("file-compare-qc-mini", template)
        self.assertNotIn("globalQcOpen", template)
        self.assertNotIn("globalQcOpen", script)
        self.assertNotIn("globalQcRows", script)
        self.assertNotIn("x-show=\"resultMode === 'qc'\"", template)
        self.assertLessEqual(template.count("QC 检查"), 2)

    def _method_body(self, source: str, start: str, end: str) -> str:
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
        match = pattern.search(source)
        self.assertIsNotNone(match, f"Missing method range {start} -> {end}")
        assert match is not None
        return match.group(0)

    def _tag_block(self, source: str, token: str) -> str:
        idx = source.find(token)
        self.assertNotEqual(idx, -1, f"Missing token {token}")
        return source[max(0, idx - 500) : idx + 3500]


if __name__ == "__main__":
    unittest.main()
