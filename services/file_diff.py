"""Structured line diff helpers for file-compare module."""

from __future__ import annotations

from difflib import SequenceMatcher

from models import DiffLine


def diff_texts(
    a: str,
    b: str,
    ignore_whitespace: bool = False,
    ignore_case: bool = False,
) -> list[DiffLine]:
    """Build structured diff rows with line numbers on both sides."""
    a_lines = a.splitlines()
    b_lines = b.splitlines()

    a_norm = [_normalize(line, ignore_whitespace, ignore_case) for line in a_lines]
    b_norm = [_normalize(line, ignore_whitespace, ignore_case) for line in b_lines]

    matcher = SequenceMatcher(None, a_norm, b_norm, autojunk=False)
    out: list[DiffLine] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                out.append(
                    DiffLine(
                        op="equal",
                        a_lineno=i + 1,
                        b_lineno=j + 1,
                        a_text=a_lines[i],
                        b_text=b_lines[j],
                    )
                )
            continue

        if tag == "delete":
            for i in range(i1, i2):
                out.append(
                    DiffLine(
                        op="delete",
                        a_lineno=i + 1,
                        b_lineno=None,
                        a_text=a_lines[i],
                        b_text="",
                    )
                )
            continue

        if tag == "insert":
            for j in range(j1, j2):
                out.append(
                    DiffLine(
                        op="insert",
                        a_lineno=None,
                        b_lineno=j + 1,
                        a_text="",
                        b_text=b_lines[j],
                    )
                )
            continue

        # replace
        a_chunk = a_lines[i1:i2]
        b_chunk = b_lines[j1:j2]
        max_len = max(len(a_chunk), len(b_chunk))
        overlap = min(len(a_chunk), len(b_chunk))

        for k in range(overlap):
            out.append(
                DiffLine(
                    op="replace",
                    a_lineno=i1 + k + 1,
                    b_lineno=j1 + k + 1,
                    a_text=a_chunk[k],
                    b_text=b_chunk[k],
                )
            )
        for k in range(overlap, len(a_chunk)):
            out.append(
                DiffLine(
                    op="delete",
                    a_lineno=i1 + k + 1,
                    b_lineno=None,
                    a_text=a_chunk[k],
                    b_text="",
                )
            )
        for k in range(overlap, len(b_chunk)):
            out.append(
                DiffLine(
                    op="insert",
                    a_lineno=None,
                    b_lineno=j1 + k + 1,
                    a_text="",
                    b_text=b_chunk[k],
                )
            )

    return out


def summarize(lines: list[DiffLine]) -> dict[str, int]:
    """Count diff rows by operation."""
    inserted = sum(1 for line in lines if line.op == "insert")
    deleted = sum(1 for line in lines if line.op == "delete")
    replaced = sum(1 for line in lines if line.op == "replace")
    equal = sum(1 for line in lines if line.op == "equal")
    return {
        "inserted": inserted,
        "deleted": deleted,
        "replaced": replaced,
        "equal": equal,
        "total": len(lines),
    }


def unified_diff_texts(
    a: str,
    b: str,
    ignore_whitespace: bool = False,
    ignore_case: bool = False,
    context_lines: int = 3,
) -> list[str]:
    """Build unified-style diff lines.

    The matcher uses normalized text (for ignore options), but emits original lines.
    """
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    a_norm = [_normalize(line, ignore_whitespace, ignore_case) for line in a_lines]
    b_norm = [_normalize(line, ignore_whitespace, ignore_case) for line in b_lines]

    matcher = SequenceMatcher(None, a_norm, b_norm, autojunk=False)
    grouped = list(matcher.get_grouped_opcodes(max(0, context_lines)))
    if not grouped:
        return []

    out: list[str] = []
    for group in grouped:
        first = group[0]
        last = group[-1]
        out.append(
            f"@@ -{_hunk_range(first[1], last[2])} +{_hunk_range(first[3], last[4])} @@"
        )
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for i in range(i1, i2):
                    out.append(f" {a_lines[i]}")
            elif tag == "delete":
                for i in range(i1, i2):
                    out.append(f"-{a_lines[i]}")
            elif tag == "insert":
                for j in range(j1, j2):
                    out.append(f"+{b_lines[j]}")
            else:
                for i in range(i1, i2):
                    out.append(f"-{a_lines[i]}")
                for j in range(j1, j2):
                    out.append(f"+{b_lines[j]}")
    return out


def _normalize(text: str, ignore_whitespace: bool, ignore_case: bool) -> str:
    s = text
    if ignore_whitespace:
        s = "".join(s.split())
    if ignore_case:
        s = s.casefold()
    return s


def _hunk_range(start: int, stop: int) -> str:
    """Return unified hunk range using 1-based line numbers."""
    length = max(0, stop - start)
    return f"{start + 1},{length}"
