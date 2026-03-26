# kmp-skills-eval

CLI tool for benchmarking agent skills against KMP sample projects. Measures skill effectiveness by running Claude with and without a skill, then grading results via file-based assertions and optional agent-based rubric evaluation.

## Architecture

Python CLI (stdlib only, no external deps). Entry point: `./eval` (Python 3 script with shebang).

```
eval                    # CLI entry point (argparse)
lib/
  util.py               # Logging, config parsing, project resolution
  workspace.py          # rsync project to temp dir
  runner.py             # Invoke `claude -p` with/without skill
  grader.py             # 11 assertion types with evidence capture
  agent_grader.py       # LLM-based rubric grading via Claude
  reporter.py           # Aggregate grading → benchmark.json + summary table
  cli.py                # Command parsing and orchestration
config/
  projects.json         # Shared project pool (pool_root + project list with tags/metadata)
  defaults.conf         # Shell-style KEY=VALUE (DEFAULT_MODEL, EVAL_TIMEOUT, etc.)
  defaults.local.conf   # Local overrides, gitignored (API keys go here)
skills/<name>/
  skill.json            # Skill config: name, description, injection type, repo
  evals/<project>.json  # Per-project: prompt + assertions + optional agent_rubric
results/                # gitignored output
```

## Key Concepts

- **Project pool**: KMP sample projects defined in `config/projects.json` (`pool_root` + project list with tags and metadata)
- **Skill**: A directory under `skills/` with `skill.json` defining how to inject knowledge into Claude (`plugin_dir` or `skill_files`)
- **Eval definition**: JSON with `eval_name`, `project`, `prompt`, `assertions[]`, and optional `agent_rubric[]`
- **Assertion types**: `file_contains`, `file_not_contains`, `file_matches`, `file_not_matches`, `file_exists`, `file_not_exists`, `file_contains_one_of`, `command_succeeds`, `file_count`, `json_path_equals`, `file_line_count`
- **Grading modes**: `rule` (deterministic assertions), `agent` (LLM-based rubric), `both`
- **Configs**: `with_skill` (Claude + skill injection) vs `without_skill` (baseline)
- **Run**: One invocation of `./eval run <skill>` produces `results/<skill>/run-<timestamp>/`

## Common Commands

```bash
./eval list-skills                                          # Show available skills
./eval list-projects                                        # Show project pool
./eval validate-skill agp9-migration                        # Validate skill config
./eval run agp9-migration --projects kampkit --dry-run      # Preview
./eval run agp9-migration --projects kampkit                # Single project, both configs
./eval run agp9-migration --projects tag:path-a             # All Path A projects
./eval run agp9-migration --grading-mode both               # All projects, rule + agent grading
./eval grade agp9-migration --grading-mode both             # Re-grade most recent run
./eval report agp9-migration                                # Regenerate report
./eval compare agp9-migration --runs run-A,run-B            # Compare two runs
```

## Setup

1. Clone this repo
2. Set up project pool: place KMP sample projects under a common root directory
3. Update `config/projects.json` with `pool_root` and project entries
4. Create `config/defaults.local.conf` with your API key: `ANTHROPIC_API_KEY=sk-ant-...`
5. Configure `skills/<name>/skill.json` with paths to your skill repos/files
6. Run: `./eval run <skill>`

## Adding a New Skill

1. Create `skills/<name>/skill.json` with `name`, `description`, `injection` config, and `repo`
2. Create `skills/<name>/evals/<project>.json` for each project
3. Run: `./eval validate-skill <name>` to verify
4. Run: `./eval run <name>`

## Dependencies

- **Skill repos**: External repos containing skill definitions. Referenced by `skill.json` → `injection.plugin_dir` or `injection.files`. The `--branch` flag checks out a branch in `repo` before running.
- **KMP samples**: Git clones of real KMP projects. Referenced by `config/projects.json` → `pool_root`. Projects are rsync'd (sans .git/build) into the results dir for each eval.
