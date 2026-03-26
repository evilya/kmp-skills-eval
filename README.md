# skills-eval

Benchmark AI agent skills against real KMP projects. Runs an agent with and without a skill, then grades results through deterministic assertions and agentic evaluation. Produces a `REPORT.md` with side-by-side comparison.

## Setup

```bash
git clone --recurse-submodules <repo-url> && cd kmp-skills-eval

# API key
export ANTHROPIC_API_KEY=sk-ant-...
# or configure in config/defaults.conf

# Project pool — clone KMP samples and list them in config/projects.json:
#   { "pool_root": "~/kmp-samples", "projects": ["kotlin-conf", "jetcaster"] }
```

## Usage

```bash
# Run agp9-migration skill on jetcaster (with and without skill, deterministic grading)
./eval run agp9-migration --projects jetcaster
```

Output: `results/agp9-migration/run-<timestamp>/REPORT.md`

```
| Metric             | With Skill | Without Skill | Delta |
|--------------------|-----------|--------------|-------|
| Deterministic pass | 86%       | 29%          | +57%  |
| Avg time           | 234s      | 188s         | +46s  |
| Avg cost           | $0.48     | $0.33        | $0.15 |
```

## CLI

```
./eval run <skill> [--projects <p1,p2>] [--config with_skill|without_skill|both]
                   [--grading-mode rule|agent|both] [--model <model>]
                   [--iterations <n>] [--branch <branch>] [--dry-run]
./eval grade <skill> [--run <id>] [--grading-mode rule|agent|both]
./eval report <skill> [--run <id>]
./eval compare <skill> --runs <id-a>,<id-b>
./eval validate-skill <skill>
./eval list-skills
./eval list-projects
```

## Adding a Skill

1. Create `skills/<name>/skill.json`:
   ```json
   {
     "name": "agp9-migration",
     "description": "Migrates KMP projects from AGP 8.x to AGP 9.0",
     "injection": { "type": "plugin_dir", "plugin_dir": "deps/kotlin-agent-skills/plugins/kotlin-agent-skills" },
     "repo": "deps/kotlin-agent-skills"
   }
   ```
   Injection types: `plugin_dir` (passes `--plugin-dir`) or `skill_files` (passes `--append-system-prompt-file` per file).

2. Create `skills/<name>/evals/<project>.json` for each project:
   ```json
   {
     "eval_name": "jetcaster-migration",
     "project": "jetcaster",
     "prompt": "Migrate this project to AGP 9.0...",
     "assertions": [
       { "name": "agp-9", "type": "file_matches", "file": "gradle/libs.versions.toml", "pattern": "\"9\\." }
     ],
     "agent_rubric": ["AGP version is 9.0+", "KMP library plugin is applied"]
   }
   ```

3. `./eval validate-skill <name> && ./eval run <name>`

## Adding a Project

Add the name to `config/projects.json` and clone the repo under `pool_root`.

## Grading

**Deterministic** (`--grading-mode rule`, default) — file assertions: `file_exists`, `file_not_exists`, `file_contains`, `file_not_contains`, `file_matches`, `file_not_matches`, `file_contains_one_of`, `command_succeeds`, `file_count`, `json_path_equals`, `file_line_count`.

**Agentic** (`--grading-mode agent`) — define `agent_rubric` as plain-text criteria; a separate agent instance evaluates each one against the modified project.
