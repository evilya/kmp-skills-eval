#!/usr/bin/env python3
"""
Score an agent's KMP-to-AGP9 migration by comparing resulting file contents
against a gold-standard state (base commit + golden patch applied).

Runs `git diff` on both --working-dir and --expected-dir, then merges the two
parsed diffs into a ScoringMap that carries explicit expected/working diff
entries alongside all scores.

Comparison methods:
  1. File-content similarity  — SequenceMatcher per file (backbone)
  2. Semantic / normalized    — whitespace+comment stripped SequenceMatcher

Combined reward:
  0.50 * file_content + 0.50 * semantic

Usage:
    python3 patch_similarity.py \
        --working-dir <agent project root> \
        --expected-dir <clean copy with patch applied> \
        --reward /logs/verifier/reward.txt
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal

from unidiff import PatchSet

RENAME_SRC_WEIGHT = 0.4
RENAME_DEST_WEIGHT = 0.6
FILE_CONTENT_REWARD_WEIGHT = 0.5
SEMANTIC_REWARD_WEIGHT = 0.5
BINARY_CHECK_BYTES = 512

INLINE_COMMENT_RE = re.compile(r"//.*$")

Operation = Literal["delete", "add", "modify", "rename"]


@dataclass
class RawDiffEntry:
    operation: Operation
    full_path: str | None
    rename_from: str | None
    rename_to: str | None
    content: list[str] | None   # text lines from base_dir; None for binary/missing


@dataclass(frozen=True)
class FileScoringEntry:
    path: str
    expected_diff: RawDiffEntry
    working_diff: RawDiffEntry | None
    weight: float
    file_content_similarity: float
    semantic_similarity: float
    combined_similarity: float


# Maps file path → its scoring entry.
ScoringMap = dict[str, FileScoringEntry]


def _is_binary(path: Path) -> bool:
    try:
        return b"\x00" in path.read_bytes()[:BINARY_CHECK_BYTES]
    except OSError:
        return False


def _read_text_lines(path: Path) -> list[str] | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


def _normalize_semantic(lines: list[str]) -> list[str]:
    """Strip blank lines and inline // comments before semantic comparison."""
    result: list[str] = []
    for line in lines:
        stripped = INLINE_COMMENT_RE.sub("", line).strip()
        if stripped:
            result.append(stripped)
    return result


def _content_ratio(a: list[str] | None, b: list[str] | None) -> float:
    if a is None or b is None:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _entry_similarity(
    expected: RawDiffEntry,
    working: RawDiffEntry | None,
) -> tuple[float, float]:
    """Return (file_content_similarity, semantic_similarity) for one file path."""

    if expected.operation == "delete":
        file_sim = 1.0 if (working is None or working.content is None) else 0.0
        return file_sim, file_sim

    if expected.operation == "rename":
        if working is None:
            return 0.0, 0.0
        src_score = 1.0 if (working.rename_from == expected.rename_from) else 0.0
        dest_ratio = _content_ratio(
            working.content if working.rename_to == expected.rename_to else None,
            expected.content,
        )
        file_sim = RENAME_SRC_WEIGHT * src_score + RENAME_DEST_WEIGHT * dest_ratio
        sem_sim = file_sim
        return file_sim, sem_sim

    # add / modify
    w_content = working.content if working is not None else None
    file_sim = _content_ratio(w_content, expected.content)

    if w_content is not None and expected.content is not None:
        sem_sim = _content_ratio(
            _normalize_semantic(w_content),
            _normalize_semantic(expected.content),
        )
    else:
        sem_sim = file_sim

    return file_sim, sem_sim


def build_scoring_map(
    expected_diffs: dict[str, RawDiffEntry],
    working_diffs: dict[str, RawDiffEntry],
) -> ScoringMap:
    """Merge expected and working diffs into a ScoringMap with per-file scores."""
    scoring_map: ScoringMap = {}

    for path, expected_entry in expected_diffs.items():
        working_entry = working_diffs.get(path)
        file_sim, sem_sim = _entry_similarity(expected_entry, working_entry)
        combined = (file_sim + sem_sim) / 2
        scoring_map[path] = FileScoringEntry(
            path=path,
            expected_diff=expected_entry,
            working_diff=working_entry,
            weight=1.0,
            file_content_similarity=file_sim,
            semantic_similarity=sem_sim,
            combined_similarity=combined,
        )

    return scoring_map


def _format_status_mark(score: float) -> str:
    if score >= 0.9:
        return "OK"
    if score > 0.0:
        return "~"
    return "NO"


def _print_report(
    scoring_map: ScoringMap,
) -> None:
    """Print a report with the most similar and least similar files."""
    entries = list(scoring_map.values())
    sorted_entries = sorted(entries, key=lambda e: -e.combined_similarity)
    top = sorted_entries[:5]
    bottom = sorted_entries[max(5, len(sorted_entries) - 5):]

    print(f"\n=== Top {len(top)} files (highest combined similarity) ===", file=sys.stderr)
    for entry in top:
        mark = _format_status_mark(entry.combined_similarity)
        print(
            f"  [{mark}] {entry.combined_similarity:.2f}"
            f"  ({entry.expected_diff.operation:6})  {entry.path}",
            file=sys.stderr,
        )

    if bottom:
        print(f"\n=== Bottom {len(bottom)} files (lowest combined similarity) ===", file=sys.stderr)
        for entry in reversed(bottom):
            mark = _format_status_mark(entry.combined_similarity)
            print(
                f"  [{mark}] {entry.combined_similarity:.2f}"
                f"  ({entry.expected_diff.operation:6})  {entry.path}",
                file=sys.stderr,
            )


def _parse_diff(patch_text: str, base_dir: Path) -> dict[str, RawDiffEntry]:
    """Parse a unified git patch using unidiff2 and return a mapping of path → RawDiffEntry."""
    result: dict[str, RawDiffEntry] = {}

    for patched_file in PatchSet(patch_text):
        if patched_file.is_removed_file:
            path = patched_file.source_file.removeprefix("a/")
            operation: Operation = "delete"
            rename_from = rename_to = None
        elif patched_file.is_rename:
            rename_from = patched_file.source_file.removeprefix("a/")
            rename_to = patched_file.target_file.removeprefix("b/")
            path = rename_to
            operation = "rename"
        elif patched_file.is_added_file:
            path = patched_file.target_file.removeprefix("b/")
            operation = "add"
            rename_from = rename_to = None
        else:
            path = patched_file.path
            operation = "modify"
            rename_from = rename_to = None

        file_path = base_dir / path
        content = None if _is_binary(file_path) else _read_text_lines(file_path)

        result[path] = RawDiffEntry(
            operation=operation,
            full_path=file_path,
            rename_from=rename_from,
            rename_to=rename_to,
            content=content,
        )

    return result


def _git_diff(directory: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(directory), "diff"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--working-dir", required=True)
    parser.add_argument("--expected-dir", required=True)
    args = parser.parse_args()

    working_path = Path(args.working_dir)
    expected_path = Path(args.expected_dir)

    expected_diff_output = _git_diff(expected_path)
    if expected_diff_output is None:
        print("ERROR: failed to compute git diff in expected-dir", file=sys.stderr)
        print("0")
        return

    working_diff_output = _git_diff(working_path)
    if working_diff_output is None:
        print("ERROR: failed to compute git diff in working-dir", file=sys.stderr)
        print("0")
        return

    expected_diffs = _parse_diff(expected_diff_output, expected_path)
    working_diffs = _parse_diff(working_diff_output, working_path)

    scoring_map = build_scoring_map(expected_diffs, working_diffs)
    _print_report(scoring_map)
    if scoring_map:
        combined_reward = sum(entry.combined_similarity for entry in scoring_map.values()) / len(scoring_map)
    else:
        combined_reward = 0.0
    print(f"{combined_reward:.2f}")


if __name__ == "__main__":
    main()
