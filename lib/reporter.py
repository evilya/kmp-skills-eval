"""Aggregate grading results into benchmark.json, REPORT.md, and print summary."""

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from .util import BOLD, NC, log_info, log_step


def generate_report(run_dir: Path, skill_name: str, model: str) -> None:
    """Generate benchmark.json and REPORT.md from all grading files in a run directory."""
    log_step("Generating benchmark report")

    # --- Collect all data ---
    collected = _collect_run_data(run_dir)
    runs = collected["runs"]
    eval_names = collected["eval_names"]
    project_data = collected["project_data"]

    with_rule_rates = collected["with_rule_rates"]
    without_rule_rates = collected["without_rule_rates"]
    with_agent_rates = collected["with_agent_rates"]
    without_agent_rates = collected["without_agent_rates"]
    with_times = collected["with_times"]
    without_times = collected["without_times"]
    with_tokens = collected["with_tokens"]
    without_tokens = collected["without_tokens"]
    with_costs = collected["with_costs"]
    without_costs = collected["without_costs"]

    def _mean(vals: list) -> float:
        return statistics.mean(vals) if vals else 0.0

    with_rule_mean = _mean(with_rule_rates)
    without_rule_mean = _mean(without_rule_rates)
    with_agent_mean = _mean(with_agent_rates)
    without_agent_mean = _mean(without_agent_rates)
    has_agent = bool(with_agent_rates or without_agent_rates)
    has_both_configs = bool(with_rule_rates and without_rule_rates)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- Write benchmark.json ---
    summary_with: dict = {
        "rule_mean_pass_rate": round(with_rule_mean, 4),
        "mean_time_seconds": round(_mean(with_times)),
        "mean_tokens": round(_mean(with_tokens)),
    }
    summary_without: dict = {
        "rule_mean_pass_rate": round(without_rule_mean, 4),
        "mean_time_seconds": round(_mean(without_times)),
        "mean_tokens": round(_mean(without_tokens)),
    }
    delta: dict = {
        "rule_pass_rate": round(with_rule_mean - without_rule_mean, 4),
        "time_seconds": round(_mean(with_times) - _mean(without_times)),
        "tokens": round(_mean(with_tokens) - _mean(without_tokens)),
    }

    if has_agent:
        summary_with["agent_mean_pass_rate"] = round(with_agent_mean, 4)
        summary_without["agent_mean_pass_rate"] = round(without_agent_mean, 4)
        delta["agent_pass_rate"] = round(with_agent_mean - without_agent_mean, 4)

    benchmark = {
        "metadata": {
            "skill_name": skill_name,
            "model": model,
            "timestamp": ts,
            "evals_count": len(eval_names),
        },
        "runs": runs,
        "summary": {
            "with_skill": summary_with,
            "without_skill": summary_without,
            "delta": delta,
        },
    }

    benchmark_file = run_dir / "benchmark.json"
    benchmark_file.write_text(json.dumps(benchmark, indent=2))
    log_info(f"Wrote {benchmark_file}")

    # --- Write REPORT.md ---
    md = _generate_markdown(
        skill_name=skill_name,
        model=model,
        timestamp=ts,
        eval_names=eval_names,
        project_data=project_data,
        has_agent=has_agent,
        has_both_configs=has_both_configs,
        with_rule_mean=with_rule_mean,
        without_rule_mean=without_rule_mean,
        with_agent_mean=with_agent_mean,
        without_agent_mean=without_agent_mean,
        with_times=with_times,
        without_times=without_times,
        with_costs=with_costs,
        without_costs=without_costs,
    )

    report_file = run_dir / "REPORT.md"
    report_file.write_text(md)
    log_info(f"Wrote {report_file}")

    # --- Print terminal summary ---
    _print_summary(runs, has_agent)


def _collect_run_data(run_dir: Path) -> dict:
    """Walk the run directory and collect all grading/timing data."""
    runs = []
    eval_names: list[str] = []
    project_data: dict[str, dict] = {}  # project -> {config -> {grading, agent_grading, timing}}

    with_rule_rates: list[float] = []
    without_rule_rates: list[float] = []
    with_agent_rates: list[float] = []
    without_agent_rates: list[float] = []
    with_times: list[float] = []
    without_times: list[float] = []
    with_tokens: list[int] = []
    without_tokens: list[int] = []
    with_costs: list[float] = []
    without_costs: list[float] = []

    for project_dir in sorted(run_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        project_name = project_dir.name
        project_data[project_name] = {}

        for config in ("with_skill", "without_skill"):
            config_dir = project_dir / config
            grading_file = config_dir / "grading.json"
            agent_grading_file = config_dir / "agent_grading.json"
            timing_file = config_dir / "timing.json"

            if not grading_file.exists() and not agent_grading_file.exists():
                continue

            timing = {}
            if timing_file.exists():
                timing = json.loads(timing_file.read_text())

            config_data: dict = {"timing": timing}

            run_entry = {
                "eval_name": project_name,
                "configuration": config,
                "result": {},
                "timing": {
                    "duration_seconds": timing.get("duration_seconds", 0),
                    "total_tokens": timing.get("total_tokens", 0),
                    "cost_usd": timing.get("cost_usd", "0"),
                },
            }

            if grading_file.exists():
                grading = json.loads(grading_file.read_text())
                config_data["grading"] = grading
                run_entry["result"]["rule"] = {
                    "pass_rate": grading["pass_rate"],
                    "passed": grading["passed"],
                    "failed": grading["failed"],
                    "total": grading["total"],
                }
                rate = grading["pass_rate"]
                if config == "with_skill":
                    with_rule_rates.append(rate)
                else:
                    without_rule_rates.append(rate)

            if agent_grading_file.exists():
                agent_grading = json.loads(agent_grading_file.read_text())
                config_data["agent_grading"] = agent_grading
                run_entry["result"]["agent"] = {
                    "pass_rate": agent_grading["pass_rate"],
                    "passed": agent_grading["passed"],
                    "failed": agent_grading["failed"],
                    "total": agent_grading["total"],
                }
                rate = agent_grading["pass_rate"]
                if config == "with_skill":
                    with_agent_rates.append(rate)
                else:
                    without_agent_rates.append(rate)

            runs.append(run_entry)
            project_data[project_name][config] = config_data

            dur = timing.get("duration_seconds", 0)
            tok = timing.get("total_tokens", 0)
            cost = float(timing.get("cost_usd", 0))
            if config == "with_skill":
                with_times.append(dur)
                with_tokens.append(tok)
                with_costs.append(cost)
            else:
                without_times.append(dur)
                without_tokens.append(tok)
                without_costs.append(cost)

            if project_name not in eval_names:
                eval_names.append(project_name)

    return {
        "runs": runs,
        "eval_names": eval_names,
        "project_data": project_data,
        "with_rule_rates": with_rule_rates,
        "without_rule_rates": without_rule_rates,
        "with_agent_rates": with_agent_rates,
        "without_agent_rates": without_agent_rates,
        "with_times": with_times,
        "without_times": without_times,
        "with_tokens": with_tokens,
        "without_tokens": without_tokens,
        "with_costs": with_costs,
        "without_costs": without_costs,
    }


def _generate_markdown(
    skill_name: str,
    model: str,
    timestamp: str,
    eval_names: list[str],
    project_data: dict[str, dict],
    has_agent: bool,
    has_both_configs: bool,
    with_rule_mean: float,
    without_rule_mean: float,
    with_agent_mean: float,
    without_agent_mean: float,
    with_times: list[float],
    without_times: list[float],
    with_costs: list[float],
    without_costs: list[float],
) -> str:
    """Generate the full Markdown report."""
    def _mean(vals: list) -> float:
        return statistics.mean(vals) if vals else 0.0

    def _pct(val: float) -> str:
        return f"{val * 100:.0f}%"

    def _delta(a: float, b: float) -> str:
        d = (a - b) * 100
        return f"{d:+.0f}%"

    def _icon(passed: bool) -> str:
        return "PASS" if passed else "FAIL"

    lines: list[str] = []

    # --- Header ---
    lines.append(f"# Benchmark Report: {skill_name}")
    lines.append("")
    lines.append(f"**Model:** {model}  ")
    lines.append(f"**Date:** {timestamp}  ")
    lines.append(f"**Projects evaluated:** {len(eval_names)}")
    lines.append("")

    # --- Overall Verdict ---
    lines.append("## Summary")
    lines.append("")

    if has_both_configs:
        lines.append("| Metric | With Skill | Without Skill | Delta |")
        lines.append("|--------|-----------|--------------|-------|")
        lines.append(f"| **Deterministic pass rate** | {_pct(with_rule_mean)} | {_pct(without_rule_mean)} | {_delta(with_rule_mean, without_rule_mean)} |")
        if has_agent:
            lines.append(f"| **Agentic pass rate** | {_pct(with_agent_mean)} | {_pct(without_agent_mean)} | {_delta(with_agent_mean, without_agent_mean)} |")
        lines.append(f"| **Avg time** | {_mean(with_times):.0f}s | {_mean(without_times):.0f}s | {_mean(with_times) - _mean(without_times):+.0f}s |")
        lines.append(f"| **Avg cost** | ${_mean(with_costs):.2f} | ${_mean(without_costs):.2f} | ${_mean(with_costs) - _mean(without_costs):+.2f} |")
    else:
        config_label = "With Skill" if with_times else "Without Skill"
        rule_mean = with_rule_mean or without_rule_mean
        agent_mean = with_agent_mean or without_agent_mean
        times = with_times or without_times
        costs = with_costs or without_costs
        lines.append(f"| Metric | {config_label} |")
        lines.append("|--------|-----------|")
        lines.append(f"| **Deterministic pass rate** | {_pct(rule_mean)} |")
        if has_agent:
            lines.append(f"| **Agentic pass rate** | {_pct(agent_mean)} |")
        lines.append(f"| **Avg time** | {_mean(times):.0f}s |")
        lines.append(f"| **Avg cost** | ${_mean(costs):.2f} |")

    lines.append("")

    # --- Results by Project (overview table) ---
    lines.append("## Results by Project")
    lines.append("")

    if has_both_configs:
        header = "| Project | With Skill | Without | Delta |"
        sep = "|---------|-----------|---------|-------|"
        if has_agent:
            header = "| Project | With (det.) | With (agent) | Without (det.) | Without (agent) | Delta (det.) | Delta (agent) |"
            sep = "|---------|------------|-------------|---------------|----------------|-------------|--------------|"
        lines.append(header)
        lines.append(sep)

        for name in eval_names:
            wd = project_data[name].get("with_skill", {})
            wod = project_data[name].get("without_skill", {})
            wr = wd.get("grading", {}).get("pass_rate")
            wor = wod.get("grading", {}).get("pass_rate")

            if has_agent:
                wa = wd.get("agent_grading", {}).get("pass_rate")
                woa = wod.get("agent_grading", {}).get("pass_rate")
                wr_s = _pct(wr) if wr is not None else "-"
                wa_s = _pct(wa) if wa is not None else "-"
                wor_s = _pct(wor) if wor is not None else "-"
                woa_s = _pct(woa) if woa is not None else "-"
                dr = _delta(wr, wor) if wr is not None and wor is not None else "-"
                da = _delta(wa, woa) if wa is not None and woa is not None else "-"
                lines.append(f"| {name} | {wr_s} | {wa_s} | {wor_s} | {woa_s} | {dr} | {da} |")
            else:
                wr_s = _pct(wr) if wr is not None else "-"
                wor_s = _pct(wor) if wor is not None else "-"
                dr = _delta(wr, wor) if wr is not None and wor is not None else "-"
                lines.append(f"| {name} | {wr_s} | {wor_s} | {dr} |")
    else:
        header = "| Project | Pass Rate |"
        sep = "|---------|-----------|"
        if has_agent:
            header = "| Project | Deterministic | Agentic |"
            sep = "|---------|--------------|---------|"
        lines.append(header)
        lines.append(sep)

        for name in eval_names:
            for cfg in ("with_skill", "without_skill"):
                cd = project_data[name].get(cfg, {})
                if not cd:
                    continue
                rr = cd.get("grading", {}).get("pass_rate")
                if has_agent:
                    ar = cd.get("agent_grading", {}).get("pass_rate")
                    lines.append(f"| {name} | {_pct(rr) if rr is not None else '-'} | {_pct(ar) if ar is not None else '-'} |")
                else:
                    lines.append(f"| {name} | {_pct(rr) if rr is not None else '-'} |")

    lines.append("")

    # --- Detailed Results per Project ---
    lines.append("## Detailed Results")
    lines.append("")

    for name in eval_names:
        lines.append(f"### {name}")
        lines.append("")

        for config in ("with_skill", "without_skill"):
            cd = project_data[name].get(config, {})
            if not cd:
                continue

            config_label = "With Skill" if config == "with_skill" else "Without Skill"
            timing = cd.get("timing", {})
            duration = timing.get("duration_seconds", 0)
            tokens = timing.get("total_tokens", 0)
            cost = timing.get("cost_usd", "0")

            lines.append(f"**{config_label}** — {duration}s, {tokens} tokens, ${cost}")
            lines.append("")

            # Deterministic assertions
            grading = cd.get("grading")
            if grading:
                assertions = grading.get("assertions", [])
                lines.append(f"Deterministic checks ({grading['passed']}/{grading['total']} passed):")
                lines.append("")
                lines.append("| Check | Result | Evidence |")
                lines.append("|-------|--------|----------|")
                for a in assertions:
                    icon = _icon(a["passed"])
                    evidence = a.get("evidence", "").replace("|", "\\|")
                    # Truncate long evidence for readability
                    if len(evidence) > 120:
                        evidence = evidence[:117] + "..."
                    lines.append(f"| {a['name']} | {icon} | {evidence} |")
                lines.append("")

            # Agent rubric
            agent_grading = cd.get("agent_grading")
            if agent_grading:
                criteria = agent_grading.get("criteria", [])
                lines.append(f"Agentic evaluation ({agent_grading['passed']}/{agent_grading['total']} passed):")
                lines.append("")
                lines.append("| Criterion | Result | Evidence |")
                lines.append("|-----------|--------|----------|")
                for c in criteria:
                    icon = _icon(c["passed"])
                    criterion_text = c.get("criterion", c.get("name", ""))
                    if len(criterion_text) > 80:
                        criterion_text = criterion_text[:77] + "..."
                    evidence = c.get("evidence", "").replace("|", "\\|").replace("\n", " ")
                    if len(evidence) > 120:
                        evidence = evidence[:117] + "..."
                    lines.append(f"| {criterion_text} | {icon} | {evidence} |")
                lines.append("")

        lines.append("---")
        lines.append("")

    # --- Footer ---
    lines.append(f"*Generated by skills-eval on {timestamp}*")
    lines.append("")

    return "\n".join(lines)


def _print_summary(runs: list[dict], has_agent: bool = False) -> None:
    """Print a human-readable summary table."""
    print()
    width = 85 if has_agent else 65
    print(f"{BOLD}{'═' * width}{NC}")
    print(f"{BOLD}  BENCHMARK RESULTS{NC}")
    print(f"{BOLD}{'═' * width}{NC}")
    print()

    if has_agent:
        print(f"  {'PROJECT':<25}  {'WITH(R)':<9} {'WITH(A)':<9}  {'W/O(R)':<9} {'W/O(A)':<9}  {'Δ(R)':<6} {'Δ(A)':<6}")
        print(f"  {'───────':<25}  {'──────':<9} {'──────':<9}  {'──────':<9} {'──────':<9}  {'───':<6} {'───':<6}")
    else:
        print(f"  {'PROJECT':<25}  {'WITH_SKILL':<12}  {'WITHOUT':<12}  {'DELTA':<8}")
        print(f"  {'───────':<25}  {'──────────':<12}  {'───────':<12}  {'─────':<8}")

    eval_names = list(dict.fromkeys(r["eval_name"] for r in runs))

    for name in eval_names:
        with_rule = None
        without_rule = None
        with_agent = None
        without_agent = None

        for r in runs:
            if r["eval_name"] == name:
                result = r.get("result", {})
                if r["configuration"] == "with_skill":
                    if "rule" in result:
                        with_rule = result["rule"]["pass_rate"]
                    if "agent" in result:
                        with_agent = result["agent"]["pass_rate"]
                elif r["configuration"] == "without_skill":
                    if "rule" in result:
                        without_rule = result["rule"]["pass_rate"]
                    if "agent" in result:
                        without_agent = result["agent"]["pass_rate"]

        if has_agent:
            wr = f"{int(with_rule * 100)}%" if with_rule is not None else "-"
            wa = f"{int(with_agent * 100)}%" if with_agent is not None else "-"
            wor = f"{int(without_rule * 100)}%" if without_rule is not None else "-"
            woa = f"{int(without_agent * 100)}%" if without_agent is not None else "-"
            dr = f"{(with_rule - without_rule) * 100:+.0f}%" if with_rule is not None and without_rule is not None else "-"
            da = f"{(with_agent - without_agent) * 100:+.0f}%" if with_agent is not None and without_agent is not None else "-"
            print(f"  {name:<25}  {wr:<9} {wa:<9}  {wor:<9} {woa:<9}  {dr:<6} {da:<6}")
        else:
            with_pct = f"{int(with_rule * 100)}%" if with_rule is not None else "-"
            without_pct = f"{int(without_rule * 100)}%" if without_rule is not None else "-"
            if with_rule is not None and without_rule is not None:
                delta_val = (with_rule - without_rule) * 100
                delta = f"{delta_val:+.0f}%"
            else:
                delta = "-"
            print(f"  {name:<25}  {with_pct:<12}  {without_pct:<12}  {delta:<8}")

    print()
    print(f"{BOLD}{'═' * width}{NC}")
    print()
