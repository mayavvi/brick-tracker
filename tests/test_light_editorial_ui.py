from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

import config
import database
from models import UserPreferences


ROOT = Path(__file__).resolve().parents[1]


class LightEditorialUiTests(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_shared_shell_is_light_only_and_cyberfx_free(self):
        base = self.read("templates/base.html")
        header = self.read("static/js/header.js")

        self.assertNotIn("cyber-fx.js", base)
        self.assertNotIn("cfx-particles", base)
        self.assertNotIn("CyberFX", base)
        self.assertNotIn("brick-theme", base)
        self.assertNotIn("classList.add('dark')", base)
        self.assertNotIn("$store.theme", base)
        self.assertNotIn("toggle theme", header.lower())
        self.assertNotIn("brick-theme", header)
        self.assertNotIn("classList.toggle(\"dark\"", header)
        self.assertIn("app-shell-header", base)
        self.assertIn("shell-module-menu", base)
        self.assertIn("shell-calendar-panel", base)
        self.assertIn("shell-user-avatar", base)
        self.assertNotIn("rounded-full bg-warm-500 text-white", base)

    def test_main_pages_use_shared_shell_without_dark_or_cyber_classes(self):
        targets = [
            "templates/welcome.html",
            "templates/tracker.html",
            "templates/file_compare.html",
            "templates/me.html",
            "templates/components/summary_cards.html",
            "templates/components/task_table.html",
        ]
        combined = "\n".join(self.read(path) for path in targets)

        self.assertNotIn("dark:", combined)
        self.assertNotIn("data-cfx", combined)
        self.assertNotIn("cfx-corners", combined)
        self.assertNotIn("cfx-spotlight", combined)
        self.assertNotIn("header-warm", self.read("templates/me.html"))
        self.assertNotIn("COMMAND DECK", self.read("templates/me.html"))
        self.assertIn("个人工作台", self.read("templates/me.html"))

    def test_me_route_keeps_shared_shell_header_enabled(self):
        me_route = self.read("routers/me.py")

        self.assertNotIn('"shell_header": False', me_route)

    def test_me_page_does_not_show_dead_csv_export_action(self):
        me = self.read("templates/me.html")

        self.assertNotIn("导出 CSV", me)
        self.assertNotIn('@click="exportCsv()"', me)
        self.assertNotIn("exportCsv()", me)

    def test_login_page_is_light_only(self):
        login = self.read("templates/login.html")

        self.assertNotIn("brick-theme", login)
        self.assertNotIn("classList.add('dark')", login)
        self.assertNotIn("dark:", login)
        self.assertIn("login-editorial", login)

    def test_preferences_model_no_longer_exposes_theme(self):
        prefs = UserPreferences()

        self.assertNotIn("theme", prefs.model_dump())


class PreferenceThemeMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_config_db = config.DATABASE_PATH
        self._orig_database_db = database.DATABASE_PATH
        self.db_path = Path(self._tmp.name) / "tracker.db"
        config.DATABASE_PATH = self.db_path
        database.DATABASE_PATH = self.db_path
        await database.close_db()
        await database.init_db()

    async def asyncTearDown(self) -> None:
        await database.close_db()
        config.DATABASE_PATH = self._orig_config_db
        database.DATABASE_PATH = self._orig_database_db
        self._tmp.cleanup()

    async def test_save_preferences_strips_legacy_theme(self):
        await database.upsert_user("alice", "Alice")
        await database.save_preferences(
            "alice",
            {
                "selected_studies": ["S1"],
                "theme": "dark",
                "tracker_aliases": ["Alice"],
            },
        )

        stored = await database.get_preferences("alice")

        self.assertEqual(stored["selected_studies"], ["S1"])
        self.assertEqual(stored["tracker_aliases"], ["Alice"])
        self.assertNotIn("theme", stored)


if __name__ == "__main__":
    unittest.main()
