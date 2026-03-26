"""Agent-based grading: uses Claude to evaluate outputs against a rubric."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .util import BLUE, GREEN, NC, RED, load_defaults, log_info, log_step, log_warn

GRADER_SYSTEM_PROMPT = """\
You are a code quality grader. You will be given a project directory that was \
modified by an AI agent. Your job is to evaluate each criterion in the rubric \
and determine if it was met.

For each criterion, respond with a JSON object in this exact format:
{
  "criteria": [
    {
      "name": "<short identifier>",
      "criterion": "<the criterion text>",
      "passed": true or false,
      "evidence": "<specific file:line evidence or explanation>"
    }
  ]
}

Rules:
- Read the actual project files to verify each criterion. Do NOT guess.
- Use the Read tool to inspect relevant files.
- Be strict: if a criterion says "must not contain X", verify it's truly absent.
- If a file doesn't exist that should, that's a failure.
- Output ONLY the JSON object, no other text.
"""


def agent_grade_eval(
    eval_file: Path,
    outputs_dir: Path,
    grading_file: Path,
    skill_description: str = "",
    model: str | None = None,
    api_key: str | None = None,
) -> dict:
    """Grade outputs using Claude as an agent grader.

    The agent reads the project files and evaluates each rubric criterion.
    """
    eval_data = json.loads(eval_file.read_text())
    eval_name = eval_data["eval_name"]
    config = outputs_dir.parent.name
    rubric = eval_data.get("agent_rubric", [])

    if not rubric:
        log_warn(f"No agent_rubric defined for {eval_name}, skipping agent grading")
        return {}

    defaults = load_defaults()
    model = model or defaults.get("GRADER_MODEL") or defaults["DEFAULT_MODEL"]
    grader_budget = defaults.get("GRADER_BUDGET_USD", "0.50")
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or defaults.get("ANTHROPIC_API_KEY")

    log_step(f"Agent grading: {eval_name} [{config}] ({len(rubric)} criteria, model={model})")

    # Use per-eval system prompt override if provided, otherwise default
    system_prompt = eval_data.get("grader_system_prompt", GRADER_SYSTEM_PROMPT)

    # Build the grading prompt
    rubric_text = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(rubric))
    task_desc = skill_description or eval_name
    prompt = f"""\
Evaluate the output of the "{task_desc}" task on this project. \
The project files are in the current directory.

## Rubric — evaluate each criterion:
{rubric_text}

Read the relevant project files and grade each criterion. Output ONLY the JSON result."""

    cmd = [
        "claude", "-p",
        "--bare",
        "--dangerously-skip-permissions",
        "--model", model,
        "--output-format", "json",
        "--max-budget-usd", str(grader_budget),
        "--system-prompt", system_prompt,
    ]

    env = os.environ.copy()
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    try:
        result = subprocess.run(
            cmd,
            cwd=outputs_dir,
            capture_output=True,
            text=True,
            input=prompt,
            env=env,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        log_warn(f"Agent grading timed out for {eval_name} [{config}]")
        return _empty_grading(eval_name, config, rubric, "Agent grading timed out")

    if result.returncode != 0:
        log_warn(f"Agent grading failed for {eval_name} [{config}]: exit {result.returncode}")
        return _empty_grading(eval_name, config, rubric, f"Exit code {result.returncode}")

    # Parse Claude's response — extract the criteria JSON
    criteria = _parse_agent_response(result.stdout, rubric)

    passed = sum(1 for c in criteria if c["passed"])
    total = len(criteria)
    failed = total - passed
    pass_rate = round(passed / total, 4) if total > 0 else 0.0

    grading = {
        "eval_name": eval_name,
        "configuration": config,
        "grading_mode": "agent",
        "grader_model": model,
        "pass_rate": pass_rate,
        "passed": passed,
        "failed": failed,
        "total": total,
        "criteria": criteria,
    }

    grading_file.parent.mkdir(parents=True, exist_ok=True)
    grading_file.write_text(json.dumps(grading, indent=2))

    if failed == 0:
        log_info(f"  {GREEN}PASS{NC} {passed}/{total} criteria (agent)")
    else:
        log_info(f"  {RED}FAIL{NC} {passed}/{total} criteria ({failed} failed) (agent)")

    return grading


def _parse_agent_response(raw_stdout: str, rubric: list[str]) -> list[dict]:
    """Parse the agent's JSON response, extracting criteria results."""
    try:
        # The output-format json wraps in a result object
        response = json.loads(raw_stdout)
        result_text = response.get("result", "") if isinstance(response, dict) else str(response)
    except json.JSONDecodeError:
        result_text = raw_stdout

    # Try to find JSON in the result text
    criteria = _extract_criteria_json(result_text)
    if criteria:
        return criteria

    # Fallback: couldn't parse agent output
    return [
        {
            "name": f"criterion-{i+1}",
            "criterion": c,
            "passed": False,
            "evidence": "Could not parse agent grading response",
        }
        for i, c in enumerate(rubric)
    ]


def _extract_criteria_json(text: str) -> list[dict] | None:
    """Try to extract criteria array from agent response text."""
    import re

    # Try direct JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "criteria" in data:
            return data["criteria"]
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON block in text
    json_match = re.search(r'\{[\s\S]*"criteria"[\s\S]*\}', text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return data.get("criteria", [])
        except json.JSONDecodeError:
            pass

    # Try to find array directly
    arr_match = re.search(r'\[[\s\S]*\]', text)
    if arr_match:
        try:
            data = json.loads(arr_match.group())
            if data and isinstance(data[0], dict) and "passed" in data[0]:
                return data
        except json.JSONDecodeError:
            pass

    return None


def _empty_grading(eval_name: str, config: str, rubric: list[str], reason: str) -> dict:
    """Return an empty grading result when agent grading fails."""
    criteria = [
        {
            "name": f"criterion-{i+1}",
            "criterion": c,
            "passed": False,
            "evidence": reason,
        }
        for i, c in enumerate(rubric)
    ]
    return {
        "eval_name": eval_name,
        "configuration": config,
        "grading_mode": "agent",
        "pass_rate": 0.0,
        "passed": 0,
        "failed": len(rubric),
        "total": len(rubric),
        "criteria": criteria,
    }
