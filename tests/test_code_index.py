from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import config
import database
import services.file_reader as file_reader
from services import code_index


class CodeIndexServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base_path = Path(self._tmp.name) / "projects"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(self._tmp.name) / "tracker.db"

        self._orig_config_base = config.PROJECTS_BASE_PATH
        self._orig_config_db = config.DATABASE_PATH
        self._orig_database_db = database.DATABASE_PATH
        self._orig_file_reader_base = file_reader.PROJECTS_BASE_PATH
        self._orig_file_reader_resolved = file_reader._PROJECTS_BASE_RESOLVED
        self._orig_index_base = code_index.PROJECTS_BASE_PATH
        self._orig_index_db = code_index.DATABASE_PATH

        config.PROJECTS_BASE_PATH = self.base_path
        config.DATABASE_PATH = self.db_path
        database.DATABASE_PATH = self.db_path
        file_reader.PROJECTS_BASE_PATH = self.base_path
        file_reader._PROJECTS_BASE_RESOLVED = self.base_path.resolve()
        code_index.PROJECTS_BASE_PATH = self.base_path
        code_index.DATABASE_PATH = self.db_path

        await database.close_db()
        await database.init_db()
        code_index._INDEX_BOOTSTRAPPED = False

    async def asyncTearDown(self) -> None:
        await database.close_db()
        config.PROJECTS_BASE_PATH = self._orig_config_base
        config.DATABASE_PATH = self._orig_config_db
        database.DATABASE_PATH = self._orig_database_db
        file_reader.PROJECTS_BASE_PATH = self._orig_file_reader_base
        file_reader._PROJECTS_BASE_RESOLVED = self._orig_file_reader_resolved
        code_index.PROJECTS_BASE_PATH = self._orig_index_base
        code_index.DATABASE_PATH = self._orig_index_db
        self._tmp.cleanup()

    async def test_rebuild_index_groups_versions_and_sorts_timeline(self) -> None:
        self._write(
            "CMPD1/PROJ1/CSR/analysis/A1.sas",
            "data step one;\nrun;\n",
        )
        self._write(
            "CMPD1/PROJ1/MDR/analysis/A1.sas",
            "data step two;\nrun;\n",
        )
        self._write(
            "CMPD1/PROJ1/CSR/qcprog/QC_A1.log",
            "qc old log\n",
        )

        result = await code_index.rebuild_index()
        self.assertEqual(result["indexed_files"], 3)

        programs = await code_index.query_program_groups(project="PROJ1")
        group = next((row for row in programs if row.program_key == "A1"), None)
        self.assertIsNotNone(group)
        self.assertEqual(group.version_count, 2)
        self.assertEqual(group.extension, ".sas")

        timeline = await code_index.get_program_timeline(
            program_key="A1",
            extension=".sas",
            project="PROJ1",
        )
        self.assertEqual(len(timeline), 2)
        self.assertGreaterEqual(
            timeline[0].modified_time.timestamp(),
            timeline[1].modified_time.timestamp(),
        )
        self.assertEqual({row.task for row in timeline}, {"CSR", "MDR"})

    async def test_parse_index_entry_extracts_context_and_skips_archive(self) -> None:
        live_file = self._write(
            "CMPD9/PROJ9/TASK9/code/t_prog.lst",
            "listing output\n",
        )
        archive_file = self._write(
            "CMPD9/PROJ9/TASK9/archive/t_prog.lst",
            "archived output\n",
        )

        parsed = code_index.parse_index_entry(live_file)
        skipped = code_index.parse_index_entry(archive_file)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["compound"], "CMPD9")
        self.assertEqual(parsed["project"], "PROJ9")
        self.assertEqual(parsed["task"], "TASK9")
        self.assertEqual(parsed["program_key"], "T_PROG")
        self.assertEqual(parsed["extension"], ".lst")
        self.assertIsNone(skipped)

    async def test_parse_index_entry_skips_temp_files_by_name(self) -> None:
        temp_sas = self._write(
            "CMPD9/PROJ9/TASK9/code/ae_temp.sas",
            "data ae;\nrun;\n",
        )
        temp_log = self._write(
            "CMPD9/PROJ9/TASK9/code/TEMP_AE.log",
            "log output\n",
        )
        normal_file = self._write(
            "CMPD9/PROJ9/TASK9/code/ae.sas",
            "data ae;\nrun;\n",
        )

        self.assertIsNone(code_index.parse_index_entry(temp_sas))
        self.assertIsNone(code_index.parse_index_entry(temp_log))
        self.assertIsNotNone(code_index.parse_index_entry(normal_file))

    async def test_query_program_groups_supports_regex_search(self) -> None:
        self._write("CMPD1/PROJ1/CSR/analysis/AE_LIST.sas", "a\n")
        self._write("CMPD1/PROJ1/CSR/analysis/CM_LIST.sas", "b\n")

        await code_index.rebuild_index()

        programs = await code_index.query_program_groups(search="re:^AE_", project="PROJ1")
        self.assertEqual(len(programs), 1)
        self.assertEqual(programs[0].program_key, "AE_LIST")

    async def test_parse_index_entry_extracts_task_path_from_sp_direct_task_folder(self) -> None:
        path = self._write(
            "QLS5132/QLS5132-101/SP/dryrun/prog/sdtm/ae.sas",
            "data ae;\nrun;\n",
        )

        parsed = code_index.parse_index_entry(path)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["compound"], "QLS5132")
        self.assertEqual(parsed["project"], "QLS5132-101")
        self.assertEqual(parsed["task"], "SP/dryrun")

    async def test_parse_index_entry_extracts_task_path_from_sp_nested_task_folder(self) -> None:
        self._write("QL1706/QL1706-307/SP/Ib\u671f/task/prog/.keep", "")
        path = self._write(
            "QL1706/QL1706-307/SP/Ib\u671f/task/prog/sdtm/ae.sas",
            "data ae;\nrun;\n",
        )

        parsed = code_index.parse_index_entry(path)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["task"], "SP/Ib\u671f/task")

    async def test_parse_index_entry_extracts_task_path_for_multiple_sp_phases(self) -> None:
        path = self._write(
            "QL1706/QL1706-307/SP/III\u671f/task/prog/sdtm/ae.sas",
            "data ae;\nrun;\n",
        )

        parsed = code_index.parse_index_entry(path)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["task"], "SP/III\u671f/task")

    async def test_parse_index_entry_skips_documents_task_sample_tree(self) -> None:
        self._write("QL1706/QL1706-304/SP/documents/task/prog/.keep", "")
        path = self._write(
            "QL1706/QL1706-304/SP/documents/task/prog/sdtm/ae.sas",
            "data ae;\nrun;\n",
        )

        parsed = code_index.parse_index_entry(path)

        self.assertIsNone(parsed)

    async def test_contexts_only_include_real_tasks_after_rebuild(self) -> None:
        self._write("QLS5132/QLS5132-101/SP/dryrun/prog/sdtm/ae.sas", "a\n")
        self._write("QL1706/QL1706-307/SP/Ib\u671f/task/prog/sdtm/ae.sas", "b\n")
        self._write("QL1706/QL1706-304/SP/documents/task/prog/sdtm/ae.sas", "c\n")

        await code_index.rebuild_index()

        contexts = await code_index.get_contexts()
        self.assertIn("SP/dryrun", contexts.tasks)
        self.assertIn("SP/Ib\u671f/task", contexts.tasks)
        self.assertNotIn("documents", contexts.tasks)
        self.assertNotIn("task", contexts.tasks)
        self.assertNotIn("SP", contexts.tasks)

    async def test_rebuild_index_initializes_database_when_connection_is_closed(self) -> None:
        self._write("CMPD2/PROJ2/TASK2/analysis/B1.sas", "proc print;\nrun;\n")

        await database.close_db()
        code_index._INDEX_BOOTSTRAPPED = False

        result = await code_index.rebuild_index()

        self.assertEqual(result["indexed_files"], 1)
        status = await code_index.get_status()
        self.assertEqual(status.indexed_files, 1)

    async def test_get_filter_options_scopes_projects_and_tasks(self) -> None:
        self._write("CMPD1/PROJ1/CSR/analysis/A1.sas", "a\n")
        self._write("CMPD1/PROJ2/CSR/analysis/A1.sas", "b\n")
        self._write("CMPD1/PROJ1/MDR/analysis/A1.sas", "c\n")

        await code_index.rebuild_index()

        opt1 = await code_index.get_filter_options(compound="CMPD1")
        self.assertEqual(set(opt1.projects), {"PROJ1", "PROJ2"})
        self.assertEqual(set(opt1.tasks), {"CSR", "MDR"})

        opt2 = await code_index.get_filter_options(compound="CMPD1", project="PROJ1")
        self.assertEqual(set(opt2.projects), {"PROJ1", "PROJ2"})
        self.assertEqual(set(opt2.tasks), {"CSR", "MDR"})

    async def test_get_qc_timing_rows_pairs_main_and_qc_logs(self) -> None:
        self._write(
            "CMPD1/PROJ1/CSR/prog/sdtm/ae.sas",
            "data ae;\nrun;\n",
        )
        self._write(
            "CMPD1/PROJ1/CSR/qcprog/sdtm/qc_ae.sas",
            "qc sas\n",
        )
        self._write(
            "CMPD1/PROJ1/CSR/qcprog/sdtm/qc_ae.log",
            "qc log older\n",
        )
        time.sleep(0.15)
        self._write(
            "CMPD1/PROJ1/CSR/outputs/ae.log",
            "main log newer\n",
        )

        await code_index.rebuild_index()

        rows = await code_index.get_qc_timing_rows(project="PROJ1", task="CSR")
        self.assertTrue(len(rows) >= 1)
        row = next((r for r in rows if r.program == "AE"), None)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertTrue(row.stale)
        self.assertEqual(row.reason, "qc-older")

    def _write(self, relative_path: str, content: str) -> Path:
        path = self.base_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
