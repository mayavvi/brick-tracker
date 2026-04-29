from __future__ import annotations

import unittest

from models import DashboardFilter, TaskItem
from services.filter import collect_persons, filter_tasks


def _task(main_person: str = "", qc_person: str = "", item: str = "x") -> TaskItem:
    return TaskItem(
        study_id="S1",
        compound="C",
        task_purpose="MDR",
        sheet_type="TFLs",
        item_name=item,
        main_person=main_person,
        qc_person=qc_person,
    )


class PersonFilterTokenizationTests(unittest.TestCase):
    def test_handover_value_matches_either_token(self) -> None:
        tasks = [
            _task(main_person="A/B", item="ab"),
            _task(main_person="A", item="solo_a"),
            _task(main_person="C", item="solo_c"),
        ]
        result = filter_tasks(tasks, DashboardFilter(person_name="B", role="main"))
        self.assertEqual([t.item_name for t in result], ["ab"])

        result_a = filter_tasks(tasks, DashboardFilter(person_name="a", role="main"))
        self.assertEqual({t.item_name for t in result_a}, {"ab", "solo_a"})

    def test_collect_persons_splits_handover_tokens(self) -> None:
        tasks = [
            _task(main_person="A/B"),
            _task(qc_person="C, D"),
            _task(main_person="E、F"),
        ]
        self.assertEqual(collect_persons(tasks), ["A", "B", "C", "D", "E", "F"])


if __name__ == "__main__":
    unittest.main()
