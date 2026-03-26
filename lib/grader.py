"""Grade eval outputs against assertions."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .util import GREEN, NC, RED, log_info, log_step


def _find_file(outputs_dir: Path, file_rel: str) -> Path | None:
    """Resolve a file path, supporting glob patterns with **."""
    if "**" in file_rel or "*" in file_rel:
        matches = list(outputs_dir.glob(file_rel))
        return matches[0] if matches else None
    return outputs_dir / file_rel


def grade_assertion(
    assertion: dict,
    outputs_dir: Path,
) -> tuple[bool, str]:
    """Grade a single assertion. Returns (passed, evidence)."""
    atype = assertion["type"]
    file_rel = assertion.get("file", assertion.get("file_pattern", ""))
    expected = assertion.get("expected", assertion.get("pattern", ""))
    expected_any = assertion.get("expected_any", [])

    target = _find_file(outputs_dir, file_rel) if file_rel else None

    if atype == "file_exists":
        if target and target.is_file():
            return True, f"File exists: {file_rel}"
        return False, f"File not found: {file_rel}"

    if atype == "file_not_exists":
        if target and target.exists():
            return False, f"File still exists: {file_rel}"
        return True, f"Confirmed absent: {file_rel}"

    if atype in ("file_contains", "file_not_contains"):
        if not target or not target.is_file():
            if atype == "file_not_contains":
                return True, f"File not found (passes negative check): {file_rel}"
            return False, f"File not found: {file_rel}"

        lines = target.read_text().splitlines()
        for i, line in enumerate(lines, 1):
            if expected in line:
                if atype == "file_contains":
                    return True, f"Found at {file_rel}:{i}: {line.strip()}"
                else:
                    return False, f"Still present at {file_rel}:{i}: {line.strip()}"

        if atype == "file_contains":
            return False, f"String not found in {file_rel}: {expected}"
        return True, f"Confirmed absent from {file_rel}: {expected}"

    if atype in ("file_matches", "file_not_matches"):
        if not target or not target.is_file():
            if atype == "file_not_matches":
                return True, f"File not found (passes negative check): {file_rel}"
            return False, f"File not found: {file_rel}"

        content = target.read_text()
        match = re.search(expected, content, re.MULTILINE)
        if match:
            # Find line number
            line_num = content[:match.start()].count("\n") + 1
            matched_line = content.splitlines()[line_num - 1].strip()
            if atype == "file_matches":
                return True, f"Matched at {file_rel}:{line_num}: {matched_line}"
            else:
                return False, f"Pattern still matches at {file_rel}:{line_num}: {matched_line}"

        if atype == "file_matches":
            return False, f"Pattern not matched in {file_rel}: {expected}"
        return True, f"Confirmed no match in {file_rel} for pattern: {expected}"

    if atype == "file_contains_one_of":
        if not target or not target.is_file():
            return False, f"File not found: {file_rel}"

        lines = target.read_text().splitlines()
        for val in expected_any:
            for i, line in enumerate(lines, 1):
                if val in line:
                    return True, f"Found '{val}' at {file_rel}:{i}: {line.strip()}"

        return False, f"None of the expected strings found in {file_rel}"

    if atype == "command_succeeds":
        command = assertion.get("command", "")
        timeout = assertion.get("timeout", 300)
        if not command:
            return False, "No command specified"
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=outputs_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0:
                return True, f"Command succeeded: {command}"
            return False, f"Command failed (exit {result.returncode}): {command}\n{result.stderr[:200]}"
        except subprocess.TimeoutExpired:
            return False, f"Command timed out after {timeout}s: {command}"

    if atype == "file_count":
        pattern = assertion.get("file_pattern", file_rel)
        min_count = assertion.get("min", 0)
        max_count = assertion.get("max", float("inf"))
        matches = list(outputs_dir.glob(pattern))
        count = len(matches)
        if min_count <= count <= max_count:
            return True, f"File count {count} within [{min_count}, {max_count}] for {pattern}"
        return False, f"File count {count} outside [{min_count}, {max_count}] for {pattern}"

    if atype == "json_path_equals":
        if not target or not target.is_file():
            return False, f"File not found: {file_rel}"
        json_path = assertion.get("path", "")
        try:
            data = json.loads(target.read_text())
            value = _resolve_json_path(data, json_path)
            if str(value) == str(expected):
                return True, f"JSON path {json_path} = {value} in {file_rel}"
            return False, f"JSON path {json_path} = {value}, expected {expected} in {file_rel}"
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            return False, f"JSON path resolution failed for {file_rel}: {e}"

    if atype == "file_line_count":
        if not target or not target.is_file():
            return False, f"File not found: {file_rel}"
        min_lines = assertion.get("min", 0)
        max_lines = assertion.get("max", float("inf"))
        count = len(target.read_text().splitlines())
        if min_lines <= count <= max_lines:
            return True, f"Line count {count} within [{min_lines}, {max_lines}] for {file_rel}"
        return False, f"Line count {count} outside [{min_lines}, {max_lines}] for {file_rel}"

    return False, f"Unknown assertion type: {atype}"


def _resolve_json_path(data, path: str):
    """Resolve a simple dot-notation JSON path (e.g. 'versions.agp')."""
    parts = path.lstrip("$.").split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise TypeError(f"Cannot traverse into {type(current)} with key '{part}'")
    return current


def grade_eval(
    eval_file: Path,
    outputs_dir: Path,
    grading_file: Path,
) -> dict:
    """Grade all assertions for an eval. Returns and writes the grading result."""
    eval_data = json.loads(eval_file.read_text())
    eval_name = eval_data["eval_name"]
    config = outputs_dir.parent.name  # "with_skill" or "without_skill"
    assertions = eval_data.get("assertions", [])

    log_step(f"Grading: {eval_name} [{config}] ({len(assertions)} assertions)")

    results = []
    passed = 0
    for assertion in assertions:
        ok, evidence = grade_assertion(assertion, outputs_dir)
        results.append({
            "name": assertion["name"],
            "passed": ok,
            "evidence": evidence,
        })
        if ok:
            passed += 1

    total = len(assertions)
    failed = total - passed
    pass_rate = round(passed / total, 4) if total > 0 else 0.0

    grading = {
        "eval_name": eval_name,
        "configuration": config,
        "pass_rate": pass_rate,
        "passed": passed,
        "failed": failed,
        "total": total,
        "assertions": results,
    }

    grading_file.parent.mkdir(parents=True, exist_ok=True)
    grading_file.write_text(json.dumps(grading, indent=2))

    if failed == 0:
        log_info(f"  {GREEN}PASS{NC} {passed}/{total} assertions")
    else:
        log_info(f"  {RED}FAIL{NC} {passed}/{total} assertions ({failed} failed)")

    return grading
