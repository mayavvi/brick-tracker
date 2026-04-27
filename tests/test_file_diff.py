from __future__ import annotations

import unittest

from services.file_diff import diff_both


class FileDiffTests(unittest.TestCase):
    def test_unified_diff_returns_real_file_line_numbers(self) -> None:
        before = "alpha\nbeta\ngamma\n"
        after = "alpha\nBETA\ngamma\ndelta\n"

        _, unified_lines = diff_both(before, after, want_unified=True)

        self.assertEqual(
            [line.model_dump() for line in unified_lines],
            [
                {"kind": "hunk", "a_lineno": None, "b_lineno": None, "text": "@@ -1,3 +1,4 @@"},
                {"kind": "context", "a_lineno": 1, "b_lineno": 1, "text": " alpha"},
                {"kind": "delete", "a_lineno": 2, "b_lineno": None, "text": "-beta"},
                {"kind": "insert", "a_lineno": None, "b_lineno": 2, "text": "+BETA"},
                {"kind": "context", "a_lineno": 3, "b_lineno": 3, "text": " gamma"},
                {"kind": "insert", "a_lineno": None, "b_lineno": 4, "text": "+delta"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
