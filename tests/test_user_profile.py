from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path


class UpsertUserPreservesDisplayNameTests(unittest.TestCase):
    """`upsert_user` must not clobber a custom display_name set via update_user_display_name."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["DATABASE_PATH"] = str(Path(self._tmp.name) / "peak.db")

        import importlib

        import config
        import database

        importlib.reload(config)
        importlib.reload(database)
        self.database = database

    def tearDown(self) -> None:
        async def _close():
            await self.database.close_db()

        asyncio.run(_close())
        os.environ.pop("DATABASE_PATH", None)
        self._tmp.cleanup()

    def test_upsert_after_custom_name_keeps_custom_name(self) -> None:
        async def scenario():
            await self.database.init_db()
            await self.database.upsert_user("local", "本机用户")
            await self.database.update_user_display_name("local", "Ekko")
            await self.database.upsert_user("local", "本机用户")
            return await self.database.get_user_profile("local")

        profile = asyncio.run(scenario())
        self.assertEqual(profile["display_name"], "Ekko")


if __name__ == "__main__":
    unittest.main()
