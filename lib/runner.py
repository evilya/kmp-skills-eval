"""Execute evaluations by invoking the claude CLI."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .util import ROOT_DIR, log_error, log_info, log_step, log_warn


def _resolve_path(p: str) -> str:
    """Resolve a path: expand ~ and make relative paths relative to ROOT_DIR."""
    path = Path(p).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return str(path)


def run_eval(
    eval_file: Path,
    config: str,
    outputs_dir: Path,
    model: str,
    max_budget: str,
    timeout_secs: int,
    injection: dict | None = None,
    api_key: str | None = None,
) -> None:
    """Run a single evaluation by invoking claude on the project.

    Args:
        eval_file: Path to the eval JSON definition.
        config: "with_skill" or "without_skill".
        outputs_dir: Directory containing the copied project files.
        model: Claude model name.
        max_budget: Max USD budget per invocation.
        timeout_secs: Timeout in seconds.
        injection: Skill injection config from skill.json (type, plugin_dir/files).
        api_key: Anthropic API key for --bare mode.
    """
    eval_data = json.loads(eval_file.read_text())
    eval_name = eval_data["eval_name"]
    prompt = eval_data["prompt"]

    # Per-eval overrides
    timeout_secs = eval_data.get("timeout_override", timeout_secs)
    max_budget = eval_data.get("budget_override", max_budget)

    # Prepend skill slash command for with_skill config
    if config == "with_skill":
        skill_command = eval_data.get("skill_command", "")
        if skill_command:
            prompt = f"{skill_command} {prompt}"

    work_dir = outputs_dir.parent  # e.g., .../with_skill/

    # Save eval metadata
    (work_dir / "eval_metadata.json").write_text(eval_file.read_text())

    log_step(f"Running eval: {eval_name} [{config}] (model={model})")

    # Build claude command.
    # --bare: skips hooks, plugins, auto-memory, CLAUDE.md auto-discovery.
    #   Ensures a completely clean environment — only explicitly provided
    #   context via --plugin-dir reaches the agent.
    # --verbose + stream-json: gives per-event output including skill/plugin info.
    cmd = [
        "claude", "-p",
        "--bare",
        "--verbose",
        "--dangerously-skip-permissions",
        "--model", model,
        "--output-format", "stream-json",
        "--max-budget-usd", str(max_budget),
    ]

    if config == "with_skill" and injection:
        inj_type = injection.get("type", "none")
        if inj_type == "plugin_dir":
            cmd.extend(["--plugin-dir", _resolve_path(injection["plugin_dir"])])
        elif inj_type == "skill_files":
            for sf in injection.get("files", []):
                cmd.extend(["--append-system-prompt-file", _resolve_path(sf)])

    # Build env with API key for --bare auth
    env = os.environ.copy()
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    # Pass prompt via stdin (avoids variadic flag issues)
    start = time.monotonic()
    exit_code = 0
    raw_output = ""
    try:
        result = subprocess.run(
            cmd,
            cwd=outputs_dir,
            capture_output=True,
            text=True,
            input=prompt,
            env=env,
            timeout=timeout_secs,
        )
        exit_code = result.returncode
        raw_output = result.stdout
        (work_dir / "claude_output.jsonl").write_text(raw_output)
        (work_dir / "claude_stderr.log").write_text(result.stderr)

        if exit_code != 0:
            log_warn(f"Eval {eval_name} [{config}] exited with code {exit_code}")

    except subprocess.TimeoutExpired as e:
        exit_code = 124
        log_warn(f"Eval {eval_name} [{config}] timed out after {timeout_secs}s")
        raw_output = (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        (work_dir / "claude_output.jsonl").write_text(raw_output)
        (work_dir / "claude_stderr.log").write_text("TIMEOUT\n")

    elapsed = int(time.monotonic() - start)

    # Parse stream-json events to extract metrics and skill triggers
    metrics = _parse_stream_events(raw_output)

    # Write timing.json
    timing = {
        "duration_seconds": elapsed,
        "total_tokens": metrics["total_tokens"],
        "cost_usd": metrics["cost_usd"],
        "num_turns": metrics["num_turns"],
        "exit_code": exit_code,
        "skills_loaded": metrics["skills_loaded"],
        "skills_triggered": metrics["skills_triggered"],
        "plugins_loaded": metrics["plugins_loaded"],
        "tool_calls": metrics["tool_calls"],
    }
    (work_dir / "timing.json").write_text(json.dumps(timing, indent=2))

    triggered = ", ".join(metrics["skills_triggered"]) if metrics["skills_triggered"] else "none"
    log_info(
        f"Completed in {elapsed}s (tokens={metrics['total_tokens']}, "
        f"cost=${metrics['cost_usd']}, skills_triggered=[{triggered}], exit={exit_code})"
    )


def _iter_json_objects(raw: str):
    """Iterate over concatenated (possibly pretty-printed) JSON objects."""
    decoder = json.JSONDecoder()
    pos = 0
    length = len(raw)
    while pos < length:
        # Skip whitespace
        while pos < length and raw[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break
        try:
            obj, end_pos = decoder.raw_decode(raw, pos)
            yield obj
            pos = end_pos
        except json.JSONDecodeError:
            pos += 1


def _parse_stream_events(raw_output: str) -> dict:
    """Parse stream-json output (pretty-printed concatenated JSON) and extract metrics + skill info."""
    total_tokens = 0
    cost_usd = "0"
    num_turns = 0
    skills_loaded: list[str] = []
    plugins_loaded: list[str] = []
    skills_triggered: list[str] = []
    tool_calls: list[str] = []

    for event in _iter_json_objects(raw_output):
        if not isinstance(event, dict):
            continue

        etype = event.get("type", "")

        # The init event lists loaded skills and plugins
        if etype == "system" and event.get("subtype") == "init":
            skills_loaded = event.get("skills", [])
            plugins_loaded = [p.get("name", "") for p in event.get("plugins", [])]

        # Assistant messages contain tool_use blocks
        if etype == "assistant":
            msg = event.get("message", {})
            if isinstance(msg, dict):
                for block in msg.get("content", []):
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        name = block.get("name", "")
                        tool_calls.append(name)
                        if name == "Skill":
                            skill_name = block.get("input", {}).get("skill", "")
                            if skill_name and skill_name not in skills_triggered:
                                skills_triggered.append(skill_name)

        # The final "result" event has aggregate metrics
        if etype == "result":
            usage = event.get("usage", {})
            total_tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            cost_usd = str(event.get("total_cost_usd", 0))
            num_turns = event.get("num_turns", 0)

    return {
        "total_tokens": total_tokens,
        "cost_usd": cost_usd,
        "num_turns": num_turns,
        "skills_loaded": skills_loaded,
        "skills_triggered": skills_triggered,
        "plugins_loaded": plugins_loaded,
        "tool_calls": tool_calls,
    }


def checkout_skill_branch(repo_path: str, branch: str) -> None:
    """Checkout a specific branch in the skill repository."""
    repo = Path(_resolve_path(repo_path))
    if not (repo / ".git").exists():
        log_error(f"Skill repo is not a git repository: {repo}")
        raise RuntimeError(f"Not a git repo: {repo}")

    log_info(f"Checking out branch '{branch}' in {repo}")
    subprocess.run(["git", "-C", str(repo), "checkout", branch, "--quiet"], check=True)
