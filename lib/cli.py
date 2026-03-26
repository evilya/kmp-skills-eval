"""CLI commands for skills-eval."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .util import (
    ROOT_DIR,
    BOLD,
    NC,
    get_eval_file,
    get_project_path,
    list_projects_table,
    list_skills,
    load_defaults,
    load_skill_json,
    log_error,
    log_info,
    log_step,
    log_warn,
    require_tool,
    resolve_projects,
    timestamp,
)
from .agent_grader import agent_grade_eval
from .grader import grade_eval
from .reporter import generate_report
from .runner import checkout_skill_branch, run_eval
from .workspace import prepare_workspace


def cmd_run(args: argparse.Namespace) -> None:
    defaults = load_defaults()
    skill_conf = load_skill_json(args.skill)

    model = args.model or defaults["DEFAULT_MODEL"]
    iterations = args.iterations or int(defaults["DEFAULT_ITERATIONS"])
    config = args.config or defaults["DEFAULT_CONFIG"]
    max_budget = defaults["MAX_BUDGET_USD"]
    timeout = int(defaults["EVAL_TIMEOUT"])

    # Build injection config from skill.json
    injection = skill_conf.get("injection")
    skill_description = skill_conf.get("description", args.skill)

    # Resolve API key: env var takes priority, then defaults.conf/local
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY") or defaults.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        log_error("ANTHROPIC_API_KEY required for --bare mode. Set it via env var or in config/defaults.local.conf")
        sys.exit(1)

    require_tool("claude")
    require_tool("rsync")

    # Checkout branch if requested
    if args.branch:
        repo = skill_conf.get("repo") or skill_conf.get("SKILL_REPO")
        if not repo:
            log_error("No 'repo' defined in skill.json — cannot use --branch")
            sys.exit(1)
        checkout_skill_branch(repo, args.branch)

    # Determine configs
    if config == "both":
        configs = ["with_skill", "without_skill"]
    else:
        configs = [config]

    # Resolve projects with eval definitions
    projects: list[str] = []
    if args.projects:
        for p in resolve_projects(args.projects):
            if get_eval_file(args.skill, p):
                projects.append(p)
            else:
                log_warn(f"No eval definition for project '{p}' under skill '{args.skill}', skipping")
    else:
        evals_dir = ROOT_DIR / "skills" / args.skill / "evals"
        for f in sorted(evals_dir.glob("*.json")):
            data = json.loads(f.read_text())
            projects.append(data["project"])

    if not projects:
        log_error("No projects to evaluate")
        sys.exit(1)

    # Create run directory
    run_id = f"run-{timestamp()}"
    run_dir = ROOT_DIR / "results" / args.skill / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    log_step(f"Starting benchmark run: {run_id}")
    log_info(f"  Skill: {args.skill}")
    log_info(f"  Model: {model}")
    log_info(f"  Projects: {', '.join(projects)}")
    log_info(f"  Configs: {', '.join(configs)}")
    log_info(f"  Iterations: {iterations}")
    log_info(f"  Run dir: {run_dir}")
    print()

    if args.dry_run:
        print(f"{BOLD}DRY RUN — commands that would be executed:{NC}")
        print()
        for project in projects:
            eval_file = get_eval_file(args.skill, project)
            prompt = json.loads(eval_file.read_text())["prompt"]
            project_path = get_project_path(project)

            for cfg in configs:
                print(f"  Project: {project} | Config: {cfg}")
                print(f"    Source: {project_path}")
                cmd = f"    claude -p --bare --verbose --dangerously-skip-permissions --model {model} --output-format stream-json --max-budget-usd {max_budget}"
                if cfg == "with_skill" and injection:
                    from .runner import _resolve_path
                    inj_type = injection.get("type", "none")
                    if inj_type == "plugin_dir":
                        cmd += f" --plugin-dir {_resolve_path(injection['plugin_dir'])}"
                    elif inj_type == "skill_files":
                        for sf in injection.get("files", []):
                            cmd += f" --append-system-prompt-file {_resolve_path(sf)}"
                cmd += f' "{prompt[:80]}..."'
                print(cmd)
                print()
        return

    # Run evaluations
    for iteration in range(1, iterations + 1):
        if iterations > 1:
            log_step(f"=== Iteration {iteration}/{iterations} ===")

        for project in projects:
            eval_file = get_eval_file(args.skill, project)
            project_path = get_project_path(project)

            if iterations > 1:
                project_dir = run_dir / f"iter-{iteration}" / project
            else:
                project_dir = run_dir / project

            for cfg in configs:
                config_dir = project_dir / cfg
                outputs_dir = config_dir / "outputs"

                prepare_workspace(project_path, outputs_dir)

                run_eval(
                    eval_file=eval_file,
                    config=cfg,
                    outputs_dir=outputs_dir,
                    model=model,
                    max_budget=max_budget,
                    timeout_secs=timeout,
                    injection=injection,
                    api_key=api_key,
                )

                grading_mode = args.grading_mode or "rule"
                if grading_mode in ("rule", "both"):
                    grade_eval(eval_file, outputs_dir, config_dir / "grading.json")
                if grading_mode in ("agent", "both"):
                    agent_grade_eval(
                        eval_file, outputs_dir, config_dir / "agent_grading.json",
                        skill_description=skill_description, api_key=api_key,
                    )
                print()

    # Generate report
    report_dir = run_dir
    if iterations > 1:
        report_dir = run_dir / f"iter-{iterations}"
    generate_report(report_dir, args.skill, model)

    print()
    log_step(f"Run complete: {run_id}")
    log_info(f"Results: {run_dir}")


def cmd_grade(args: argparse.Namespace) -> None:
    skill_conf = load_skill_json(args.skill)
    skill_description = skill_conf.get("description", args.skill)

    run_id = args.run
    results_dir = ROOT_DIR / "results" / args.skill

    if not run_id:
        runs = sorted(results_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if not runs:
            log_error(f"No runs found for skill '{args.skill}'")
            sys.exit(1)
        run_id = runs[0].name
        log_info(f"Using most recent run: {run_id}")

    run_dir = results_dir / run_id
    if not run_dir.is_dir():
        log_error(f"Run directory not found: {run_dir}")
        sys.exit(1)

    grading_mode = args.grading_mode or "rule"

    # Resolve API key for agent grading
    api_key = None
    if grading_mode in ("agent", "both"):
        import os
        defaults = load_defaults()
        api_key = os.environ.get("ANTHROPIC_API_KEY") or defaults.get("ANTHROPIC_API_KEY")
        if not api_key:
            log_error("ANTHROPIC_API_KEY required for agent grading")
            sys.exit(1)

    log_step(f"Re-grading run: {run_id} (mode={grading_mode})")

    for project_dir in sorted(run_dir.iterdir()):
        if not project_dir.is_dir() or project_dir.name.startswith("iter-"):
            continue

        eval_file = get_eval_file(args.skill, project_dir.name)
        if not eval_file:
            log_warn(f"No eval file for {project_dir.name}, skipping")
            continue

        for cfg in ("with_skill", "without_skill"):
            config_dir = project_dir / cfg
            if (config_dir / "outputs").is_dir():
                if grading_mode in ("rule", "both"):
                    grade_eval(eval_file, config_dir / "outputs", config_dir / "grading.json")
                if grading_mode in ("agent", "both"):
                    agent_grade_eval(
                        eval_file, config_dir / "outputs", config_dir / "agent_grading.json",
                        skill_description=skill_description, api_key=api_key,
                    )

    log_step("Re-grading complete")


def cmd_report(args: argparse.Namespace) -> None:
    load_skill_json(args.skill)
    defaults = load_defaults()
    model = args.model or defaults["DEFAULT_MODEL"]

    run_id = args.run
    results_dir = ROOT_DIR / "results" / args.skill

    if not run_id:
        runs = sorted(results_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if not runs:
            log_error(f"No runs found for skill '{args.skill}'")
            sys.exit(1)
        run_id = runs[0].name
        log_info(f"Using most recent run: {run_id}")

    run_dir = results_dir / run_id
    if not run_dir.is_dir():
        log_error(f"Run directory not found: {run_dir}")
        sys.exit(1)

    generate_report(run_dir, args.skill, model)


def _resolve_skill_path(p: str) -> Path:
    """Resolve a path from skill config: expand ~ and make relative paths relative to ROOT_DIR."""
    path = Path(p).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def cmd_validate_skill(args: argparse.Namespace) -> None:
    """Validate a skill configuration: skill.json, eval files, project references."""
    skill = args.skill
    skill_dir = ROOT_DIR / "skills" / skill
    errors: list[str] = []
    warnings: list[str] = []

    # Check skill.json
    json_path = skill_dir / "skill.json"
    if not json_path.exists():
        conf_path = skill_dir / "skill.conf"
        if conf_path.exists():
            warnings.append(f"Using deprecated skill.conf — migrate to skill.json")
        else:
            errors.append(f"No skill.json found at {json_path}")
            _print_validation(skill, errors, warnings)
            return

    try:
        skill_conf = load_skill_json(skill)
    except SystemExit:
        errors.append(f"Failed to load skill config")
        _print_validation(skill, errors, warnings)
        return

    # Check injection references
    injection = skill_conf.get("injection", {})
    inj_type = injection.get("type", "none")
    if inj_type == "plugin_dir":
        plugin_dir = _resolve_skill_path(injection.get("plugin_dir", ""))
        if not plugin_dir.is_dir():
            errors.append(f"Plugin directory not found: {plugin_dir}")
    elif inj_type == "skill_files":
        for sf in injection.get("files", []):
            sf_path = _resolve_skill_path(sf)
            if not sf_path.is_file():
                errors.append(f"Skill file not found: {sf_path}")

    # Check repo
    repo = skill_conf.get("repo")
    if repo:
        repo_path = _resolve_skill_path(repo)
        if not repo_path.is_dir():
            warnings.append(f"Repo directory not found: {repo_path}")

    # Check eval files
    evals_dir = skill_dir / "evals"
    if not evals_dir.is_dir():
        errors.append(f"No evals/ directory found")
    else:
        from .util import load_projects
        pool = load_projects()
        project_names = set(pool["projects"])

        for eval_file in sorted(evals_dir.glob("*.json")):
            try:
                data = json.loads(eval_file.read_text())
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in {eval_file.name}: {e}")
                continue

            if "eval_name" not in data:
                errors.append(f"{eval_file.name}: missing 'eval_name'")
            if "prompt" not in data:
                errors.append(f"{eval_file.name}: missing 'prompt'")

            project = data.get("project", "")
            if project and project not in project_names:
                warnings.append(f"{eval_file.name}: project '{project}' not in projects.json")

    _print_validation(skill, errors, warnings)


def _print_validation(skill: str, errors: list[str], warnings: list[str]) -> None:
    from .util import GREEN, RED, YELLOW
    if errors:
        log_error(f"Validation FAILED for skill '{skill}':")
        for e in errors:
            print(f"  {RED}✗{NC} {e}")
    if warnings:
        for w in warnings:
            print(f"  {YELLOW}⚠{NC} {w}")
    if not errors:
        print(f"  {GREEN}✓{NC} Skill '{skill}' is valid ({len(warnings)} warnings)")


def cmd_compare(args: argparse.Namespace) -> None:
    """Compare two runs side by side."""
    skill = args.skill
    run_ids = [r.strip() for r in args.runs.split(",")]
    if len(run_ids) != 2:
        log_error("--runs requires exactly two run IDs separated by comma")
        sys.exit(1)

    results_dir = ROOT_DIR / "results" / skill
    benchmarks = []
    for run_id in run_ids:
        bench_file = results_dir / run_id / "benchmark.json"
        if not bench_file.exists():
            log_error(f"No benchmark.json found for run '{run_id}'")
            sys.exit(1)
        benchmarks.append(json.loads(bench_file.read_text()))

    print()
    print(f"{BOLD}{'═' * 75}{NC}")
    print(f"{BOLD}  COMPARISON: {run_ids[0]} vs {run_ids[1]}{NC}")
    print(f"{BOLD}{'═' * 75}{NC}")
    print()
    print(f"  {'PROJECT':<25}  {'RUN A':<12}  {'RUN B':<12}  {'DELTA':<8}")
    print(f"  {'───────':<25}  {'─────':<12}  {'─────':<12}  {'─────':<8}")

    # Build lookup: project -> with_skill pass_rate for each benchmark
    def _build_rates(bench: dict) -> dict[str, float | None]:
        rates = {}
        for run in bench["runs"]:
            name = run["eval_name"]
            if run["configuration"] == "with_skill":
                result = run.get("result", {})
                # Support both old and new format
                if "rule" in result:
                    rates[name] = result["rule"]["pass_rate"]
                elif "pass_rate" in result:
                    rates[name] = result["pass_rate"]
        return rates

    rates_a = _build_rates(benchmarks[0])
    rates_b = _build_rates(benchmarks[1])

    all_projects = list(dict.fromkeys(list(rates_a.keys()) + list(rates_b.keys())))
    for name in all_projects:
        ra = rates_a.get(name)
        rb = rates_b.get(name)
        sa = f"{int(ra * 100)}%" if ra is not None else "-"
        sb = f"{int(rb * 100)}%" if rb is not None else "-"
        if ra is not None and rb is not None:
            delta = f"{(rb - ra) * 100:+.0f}%"
        else:
            delta = "-"
        print(f"  {name:<25}  {sa:<12}  {sb:<12}  {delta:<8}")

    print()

    # Summary
    sa = benchmarks[0].get("summary", {}).get("with_skill", {})
    sb = benchmarks[1].get("summary", {}).get("with_skill", {})
    ma = sa.get("rule_mean_pass_rate", sa.get("mean_pass_rate", 0))
    mb = sb.get("rule_mean_pass_rate", sb.get("mean_pass_rate", 0))
    print(f"  Mean pass rate:  A={int(ma * 100)}%  B={int(mb * 100)}%  Δ={(mb - ma) * 100:+.0f}%")
    print()
    print(f"{BOLD}{'═' * 75}{NC}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="eval",
        description="skills-eval — Benchmark AI agent skills against KMP projects",
    )
    subparsers = parser.add_subparsers(dest="command")

    # run
    p_run = subparsers.add_parser("run", help="Run evaluations")
    p_run.add_argument("skill", help="Skill name (e.g., agp9-migration)")
    p_run.add_argument("--projects", help="Filter projects: csv list (e.g., kampkit,jetcaster)")
    p_run.add_argument("--config", choices=["with_skill", "without_skill", "both"], help="Which configs to run (default: both)")
    p_run.add_argument("--iterations", type=int, help="Number of iterations (default: 1)")
    p_run.add_argument("--model", help="Claude model (default: from defaults.conf)")
    p_run.add_argument("--branch", help="Checkout this branch in skill repo before running")
    p_run.add_argument("--grading-mode", choices=["rule", "agent", "both"], help="Grading mode (default: rule)")
    p_run.add_argument("--dry-run", action="store_true", help="Print commands without executing")

    # grade
    p_grade = subparsers.add_parser("grade", help="Re-grade existing outputs")
    p_grade.add_argument("skill", help="Skill name")
    p_grade.add_argument("--run", help="Run ID (default: most recent)")
    p_grade.add_argument("--grading-mode", choices=["rule", "agent", "both"], help="Grading mode (default: rule)")

    # report
    p_report = subparsers.add_parser("report", help="Regenerate benchmark report")
    p_report.add_argument("skill", help="Skill name")
    p_report.add_argument("--run", help="Run ID (default: most recent)")
    p_report.add_argument("--model", help="Model to record in metadata")

    # validate-skill
    p_validate = subparsers.add_parser("validate-skill", help="Validate skill configuration")
    p_validate.add_argument("skill", help="Skill name to validate")

    # compare
    p_compare = subparsers.add_parser("compare", help="Compare two runs side by side")
    p_compare.add_argument("skill", help="Skill name")
    p_compare.add_argument("--runs", required=True, help="Two run IDs separated by comma (e.g., run-A,run-B)")

    # list-projects
    subparsers.add_parser("list-projects", help="Show project pool")

    # list-skills
    subparsers.add_parser("list-skills", help="Show available skills")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "grade":
        cmd_grade(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "validate-skill":
        cmd_validate_skill(args)
    elif args.command == "compare":
        cmd_compare(args)
    elif args.command == "list-projects":
        list_projects_table()
    elif args.command == "list-skills":
        skills = list_skills()
        print(f"{BOLD}{'NAME':<30} {'TYPE':<15} {'EVALS':<8} DESCRIPTION{NC}")
        print(f"{'----':<30} {'----':<15} {'-----':<8} -----------")
        for s in skills:
            print(f"{s['name']:<30} {s['injection_type']:<15} {s['eval_count']:<8} {s['description']}")
    else:
        parser.print_help()
        sys.exit(1)
