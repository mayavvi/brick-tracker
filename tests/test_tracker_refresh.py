from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from pydantic import ValidationError

from models import DashboardFilter, TaskItem
from services.filter import build_summary


ROOT = Path(__file__).resolve().parents[1]


class TrackerRoleFilterTests(unittest.TestCase):
    def test_dashboard_filter_defaults_to_main_and_rejects_all(self) -> None:
        self.assertEqual(DashboardFilter().role, "main")

        with self.assertRaises(ValidationError):
            DashboardFilter(role="all")

    def test_role_summary_counts_only_selected_side(self) -> None:
        tasks = [
            TaskItem(
                study_id="S1",
                compound="C",
                task_purpose="MDR",
                sheet_type="TFLs",
                item_name="A",
                main_status="已完成，可以QC",
                qc_status="进行中",
                ddl=date(2026, 4, 25),
            ),
            TaskItem(
                study_id="S1",
                compound="C",
                task_purpose="MDR",
                sheet_type="TFLs",
                item_name="B",
                main_status="进行中",
                qc_status="有问题，请修改",
                ddl=date(2026, 4, 26),
            ),
        ]

        main_summary = build_summary(tasks, role="main")
        qc_summary = build_summary(tasks, role="qc")

        self.assertEqual(main_summary.in_progress, 1)
        self.assertEqual(main_summary.completed_ready_qc, 1)
        self.assertEqual(main_summary.has_issues, 1)
        self.assertEqual(qc_summary.in_progress, 1)
        self.assertEqual(qc_summary.completed_ready_qc, 1)
        self.assertEqual(qc_summary.has_issues, 1)


class TrackerDashboardScanTests(unittest.TestCase):
    def test_study_id_search_scans_prefixed_compound_before_global_fallback(self) -> None:
        from models import StudyInfo
        import services.scanner as scanner

        calls: list[str | None] = []
        original_compounds = scanner.discover_compounds
        original_studies = scanner.discover_studies

        def fake_compounds(_base_path):
            return ["QLC5508", "QLC7401"]

        def fake_studies(_base_path, compound=None):
            calls.append(compound)
            if compound is None:
                raise AssertionError("study-id search must not trigger a global scan")
            if compound == "QLC5508":
                return [StudyInfo(compound="QLC5508", study_id="QLC5508-201", tracker_files=[])]
            return []

        try:
            scanner.discover_compounds = fake_compounds
            scanner.discover_studies = fake_studies

            matches = scanner.search_studies(Path("C:/Projects"), "QLC5508-201")
        finally:
            scanner.discover_compounds = original_compounds
            scanner.discover_studies = original_studies

        self.assertEqual(calls, ["QLC5508"])
        self.assertEqual([study.study_id for study in matches], ["QLC5508-201"])

    def test_selected_study_loading_scans_only_candidate_compound(self) -> None:
        from models import StudyInfo, TrackerFileInfo
        import routers.dashboard as dashboard

        tracker_file = TrackerFileInfo(
            file_path="C:/Projects/QLC5508/QLC5508-201/tracker.xlsx",
            file_name="tracker.xlsx",
            task_purpose="dryrun",
            study_id="QLC5508-201",
            compound="QLC5508",
            last_modified=1.0,
        )
        study = StudyInfo(compound="QLC5508", study_id="QLC5508-201", tracker_files=[tracker_file])
        calls: list[str | None] = []
        original_discover = dashboard.discover_studies
        original_cache = dashboard.tracker_cache

        class FakeCache:
            def get_tasks(self, file_info):
                return [TaskItem(study_id=file_info.study_id, compound=file_info.compound, task_purpose=file_info.task_purpose, sheet_type="SPEC")]

        def fake_discover(_base_path, compound=None):
            calls.append(compound)
            if compound is None:
                raise AssertionError("selected dashboard loading must not trigger a global scan")
            if compound == "QLC5508":
                return [study]
            return []

        try:
            dashboard.discover_studies = fake_discover
            dashboard.tracker_cache = FakeCache()

            tasks = dashboard._load_tasks_for_studies(["QLC5508-201"], [tracker_file.file_path])
        finally:
            dashboard.discover_studies = original_discover
            dashboard.tracker_cache = original_cache

        self.assertEqual(calls, ["QLC5508"])
        self.assertEqual(len(tasks), 1)


class TrackerUiRefreshTests(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_tracker_role_control_only_exposes_main_and_qc(self) -> None:
        tracker = self.read("templates/tracker.html")
        app_js = self.read("static/js/app.js")

        self.assertIn("{v:'main',l:'搬砖'}", tracker)
        self.assertIn("{v:'qc',l:'找茬'}", tracker)
        self.assertNotIn("{v:'all',l:'全部'}", tracker)
        self.assertIn('roleFilter: "main"', app_js)
        self.assertIn("_normalizeRoleFilter", app_js)

    def test_tracker_hud_is_owned_by_tracker_app(self) -> None:
        tracker = self.read("templates/tracker.html")
        app_js = self.read("static/js/app.js")

        self.assertIn("tracker-hud-ticker", tracker)
        self.assertIn("initHudTicker", app_js)
        self.assertIn("ONLINE ·", app_js)
        self.assertNotIn("cfx-hud-ticker", tracker)

    def test_radar_uses_static_pressure_zones_without_sweep(self) -> None:
        radar = self.read("static/js/radar.js")

        self.assertIn("PRESSURE_ZONES", radar)
        self.assertIn("MAX_RADAR_DAYS = 14", radar)
        self.assertIn("drawPressureZones", radar)
        self.assertNotIn("_sweep", radar)
        self.assertNotIn("Sweep trail", radar)
        self.assertNotIn("+14d", radar)

    def test_tracker_scroll_and_palette_hooks_exist(self) -> None:
        css = self.read("static/css/style.css")
        table = self.read("templates/components/task_table.html")

        self.assertIn(".tracker-page", css)
        self.assertIn(".tracker-table-card", css)
        self.assertIn("tracker-table-scroll", table)

    def test_summary_cards_are_inside_collapsible_pivot_panel(self) -> None:
        tracker = self.read("templates/tracker.html")

        summary_pos = tracker.index('{% include "components/summary_cards.html" %}')
        pivot_pos = tracker.index("◆ 数据透视 · DASHBOARD")
        table_pos = tracker.index('{% include "components/task_table.html" %}')
        collapsed_region = tracker[pivot_pos:table_pos]

        self.assertGreater(summary_pos, pivot_pos)
        self.assertLess(summary_pos, table_pos)
        self.assertIn('x-show="showCharts"', collapsed_region)
        self.assertIn("数据汇总", collapsed_region)

    def test_task_table_uses_page_vertical_scroll_only(self) -> None:
        css = self.read("static/css/style.css")

        scroll_rule_start = css.index(".tracker-table-scroll")
        scroll_rule = css[scroll_rule_start:css.index("}", scroll_rule_start)]

        self.assertIn("overflow-x: auto", scroll_rule)
        self.assertIn("overflow-y: visible", scroll_rule)
        self.assertNotIn("overscroll-behavior", scroll_rule)

    def test_status_badges_use_phase_color_tokens(self) -> None:
        app_js = self.read("static/js/app.js")

        self.assertIn('关闭问题: "tracker-status-badge tracker-status-done"', app_js)
        self.assertIn('"已完成，可以QC": "tracker-status-badge tracker-status-qc-ready"', app_js)
        self.assertIn('进行中: "tracker-status-badge tracker-status-active"', app_js)
        self.assertIn('"有问题，请修改": "tracker-status-badge tracker-status-rework"', app_js)
        self.assertIn('"待定，请留意": "tracker-status-badge tracker-status-paused"', app_js)
        self.assertIn('"tracker-status-badge tracker-status-empty"', app_js)

    def test_dashboard_updates_do_not_force_replay_enter_animation(self) -> None:
        tracker = self.read("templates/tracker.html")
        app_js = self.read("static/js/app.js")

        self.assertNotIn(':key="animationKey"', tracker)
        self.assertNotIn("animationKey++", app_js)

    def test_restoring_saved_selection_does_not_replay_search_scan(self) -> None:
        app_js = self.read("static/js/app.js")

        restore_start = app_js.index("if (this.selectedStudies.length > 0)")
        restore_block = app_js[restore_start:app_js.index("_setupKeyboard", restore_start)]

        self.assertIn("await this.loadDashboard();", restore_block)
        self.assertNotIn("await this.searchStudies();", restore_block)

    def test_tracker_sidebar_has_reliable_collapse_and_bottom_action_layout(self) -> None:
        tracker = self.read("templates/tracker.html")

        self.assertIn("tracker-sidebar-expand-toggle", tracker)
        self.assertIn("z-10", tracker)
        self.assertIn('class="sidebar-scroll flex-1 space-y-5 overflow-y-auto pr-1"', tracker)
        self.assertIn('class="sidebar-footer shrink-0 pt-3"', tracker)

    def test_tracker_page_disables_continuous_status_pulse(self) -> None:
        css = self.read("static/css/style.css")

        selector = ".tracker-page .ddl-overdue::before,"
        rule_start = css.index(selector)
        rule = css[rule_start:css.index("}", rule_start)]

        self.assertIn("animation: none", rule)


if __name__ == "__main__":
    unittest.main()
