"""Structured line diff helpers for file-compare module."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher

from models import DiffLine, UnifiedDiffLine


def _prepare_diff(
    a: str,
    b: str,
    ignore_whitespace: bool,
    ignore_case: bool,
) -> tuple[list[str], list[str], SequenceMatcher]:
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    a_norm = [_normalize(line, ignore_whitespace, ignore_case) for line in a_lines]
    b_norm = [_normalize(line, ignore_whitespace, ignore_case) for line in b_lines]
    return a_lines, b_lines, SequenceMatcher(None, a_norm, b_norm, autojunk=False)


def diff_texts(
    a: str,
    b: str,
    ignore_whitespace: bool = False,
    ignore_case: bool = False,
) -> list[DiffLine]:
    """Build structured diff rows with line numbers on both sides."""
    a_lines, b_lines, matcher = _prepare_diff(a, b, ignore_whitespace, ignore_case)
    return _diff_from_matcher(matcher, a_lines, b_lines)

def diff_both(
    a: str,
    b: str,
    ignore_whitespace: bool = False,
    ignore_case: bool = False,
    context_lines: int = 3,
    want_unified: bool = False,
) -> tuple[list[DiffLine], list[UnifiedDiffLine]]:
    """Build side-by-side rows and, optionally, unified lines from one matcher."""
    a_lines, b_lines, matcher = _prepare_diff(a, b, ignore_whitespace, ignore_case)
    side_lines = _diff_from_matcher(matcher, a_lines, b_lines)
    unified_lines = _unified_from_matcher(
        matcher,
        a_lines,
        b_lines,
        context_lines=context_lines,
    ) if want_unified else []
    return side_lines, unified_lines


def summarize(lines: list[DiffLine]) -> dict[str, int]:
    """Count diff rows by operation."""
    counts = Counter(line.op for line in lines)
    return {
        "inserted": counts["insert"],
        "deleted": counts["delete"],
        "replaced": counts["replace"],
        "equal": counts["equal"],
        "total": len(lines),
    }


def unified_diff_texts(
    a: str,
    b: str,
    ignore_whitespace: bool = False,
    ignore_case: bool = False,
    context_lines: int = 3,
) -> list[UnifiedDiffLine]:
    """Build unified-style diff lines.

    The matcher uses normalized text (for ignore options), but emits original lines.
    """
    a_lines, b_lines, matcher = _prepare_diff(a, b, ignore_whitespace, ignore_case)
    return _unified_from_matcher(
        matcher,
        a_lines,
        b_lines,
        context_lines=context_lines,
    )


def _diff_from_matcher(
    matcher: SequenceMatcher,
    a_lines: list[str],
    b_lines: list[str],
) -> list[DiffLine]:
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

        a_chunk = a_lines[i1:i2]
        b_chunk = b_lines[j1:j2]
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


def _unified_from_matcher(
    matcher: SequenceMatcher,
    a_lines: list[str],
    b_lines: list[str],
    context_lines: int,
) -> list[UnifiedDiffLine]:
    grouped = list(matcher.get_grouped_opcodes(max(0, context_lines)))
    if not grouped:
        return []

    out: list[UnifiedDiffLine] = []
    for group in grouped:
        first = group[0]
        last = group[-1]
        out.append(
            UnifiedDiffLine(
                kind="hunk",
                a_lineno=None,
                b_lineno=None,
                text=f"@@ -{_hunk_range(first[1], last[2])} +{_hunk_range(first[3], last[4])} @@",
            )
        )
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for i in range(i1, i2):
                    out.append(
                        UnifiedDiffLine(
                            kind="context",
                            a_lineno=i + 1,
                            b_lineno=i - i1 + j1 + 1,
                            text=f" {a_lines[i]}",
                        )
                    )
            elif tag == "delete":
                for i in range(i1, i2):
                    out.append(
                        UnifiedDiffLine(
                            kind="delete",
                            a_lineno=i + 1,
                            b_lineno=None,
                            text=f"-{a_lines[i]}",
                        )
                    )
            elif tag == "insert":
                for j in range(j1, j2):
                    out.append(
                        UnifiedDiffLine(
                            kind="insert",
                            a_lineno=None,
                            b_lineno=j + 1,
                            text=f"+{b_lines[j]}",
                        )
                    )
            else:
                for i in range(i1, i2):
                    out.append(
                        UnifiedDiffLine(
                            kind="delete",
                            a_lineno=i + 1,
                            b_lineno=None,
                            text=f"-{a_lines[i]}",
                        )
                    )
                for j in range(j1, j2):
                    out.append(
                        UnifiedDiffLine(
                            kind="insert",
                            a_lineno=None,
                            b_lineno=j + 1,
                            text=f"+{b_lines[j]}",
                        )
                    )
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
