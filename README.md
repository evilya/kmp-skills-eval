# kmp-skills-eval

A/B evaluations of the [`kotlin-tooling-agp9-migration`](https://github.com/Kotlin/kotlin-agent-skills/tree/main/skills/kotlin-tooling-agp9-migration) skill on real KMP projects, run through [JetBrains/skills-ab-eval](https://github.com/JetBrains/skills-ab-eval). Each evaluation runs an LLM agent on the same project twice — with and without the skill mounted — and grades the resulting migration on 9 structural and build criteria.

## Headline results (Claude Opus 4.7, single trial each)

| Project | Without skill | With skill | Δ |
|---|---|---|---|
| **kotlinconf-app** | 0.224 | **0.965** | **+0.740** |
| **kmm-rss-reader** | 0.183 | **0.883** | **+0.700** |

Both projects exhibit the same pattern: the skill teaches the **AGP 9 migration trigger condition** (a module combining `kotlin.multiplatform` with `com.android.application` requires extraction into a standalone Android app module). Without the skill the agent edits in place and leaves the structural problem intact, producing no working build. With the skill it correctly performs the Path B restructure and reaches a green `./gradlew assembleDebug` + green unit tests.

Per-project breakdowns: [`results/kotlinconf-app/REPORT.md`](results/kotlinconf-app/REPORT.md), [`results/kmm-rss-reader/REPORT.md`](results/kmm-rss-reader/REPORT.md).

## Why these two projects

The skill addresses a narrow but real Android Gradle Plugin 9.0 incompatibility: AGP 9 forbids the Kotlin Multiplatform plugin and the Android Application plugin from coexisting in the same Gradle module. Projects in this state must be restructured — the skill's job is to teach the agent the right restructure pattern.

- **kotlinconf-app** is the JetBrains KotlinConf event app. The base commit has `:androidApp` combining KMP + `com.android.application`, plus three KMP library modules using the old `com.android.library` plugin — a full multi-module migration scenario.
- **kmm-rss-reader** is the JetBrains "kmm-production-sample" RSS reader. The base commit has `:composeApp` combining KMP + `com.android.application`, plus a `:shared` library module — a smaller but still non-trivial scenario.

A third task — `jetcaster` — is included in `tasks/` but **was not run**. The jetcaster repo at the tested base commit already uses the new `com.android.kotlin.multiplatform.library` plugin in most places, so most of the binary checks already pass at base. It's not a discriminating test for this skill.

## How the verifier scores a migration

Each project's `tests/test.sh` runs after the agent finishes. It computes a weighted reward over:

| Category | Weight | What it measures |
|---|---|---|
| 5 binary structural checks | 50% | AGP version ≥ 9; no KMP+application combo in any module; android app extracted to a standalone module; built-in Kotlin used (no `org.jetbrains.kotlin.android`); KMP modules use `com.android.kotlin.multiplatform.library` |
| Per-platform builds | 30–35% | `:<discovered-android>:assembleDebug`; `:<discovered-desktop>:assemble`; `:<discovered-web>:wasmJsBrowserDevelopmentExecutableDistribution` (kotlinconf only). Modules are discovered dynamically via `analyze_plugins.py` so the verifier doesn't care whether the agent picked `:androidApp`, `:mobile`, or any other name. |
| Tests | 10% | `:<discovered-android>:testDebugUnitTest jvmTest` |
| Patch similarity | 5% | Per-file `SequenceMatcher` against the gold-standard `fix.patch` (where one exists) |
| Agent process | 5% | Agent invoked gradle build + tests during its session; agent used TodoWrite |

The verifier uses **module discovery**, not hard-coded paths — so it scores any structurally correct migration (Path A, Path B, or Path C) the same way. If a project doesn't have a desktop module in the gold-standard state (jetcaster, kmm-rss-reader), the desktop weight redistributes into the Android build slot rather than punishing the agent for "missing" a module it was never supposed to create.

## Reproducing the results

Prerequisites:
- Python 3.11+, [uv](https://github.com/astral-sh/uv)
- [Harbor CLI](https://github.com/harbor-framework/harbor) on `PATH` (`uv tool install harbor`)
- Docker daemon running (each task spins up a Linux container with JDK 17/21, Gradle 9.1, Android SDK 35; allocate ≥16 GB memory)
- `ANTHROPIC_API_KEY` in env (the harbor agent runs Claude on the host, then mounts results into the container for verification)

```bash
# 1. Clone JetBrains/skills-ab-eval (the A/B harness) and install it
git clone https://github.com/JetBrains/skills-ab-eval.git
cd skills-ab-eval
uv venv .venv && uv pip install -e .
source .venv/bin/activate

# 2. Clone the skill repo
git clone https://github.com/Kotlin/kotlin-agent-skills.git ../kotlin-agent-skills

# 3. From this repo: run the kotlinconf A/B (≈30 min, ~$2 in Opus tokens)
cd ../kmp-skills-eval
skills-ab-eval run \
  --task tasks/kotlinconf-agp9-migration-task \
  --skill ../kotlin-agent-skills/skills/kotlin-tooling-agp9-migration \
  --model anthropic/claude-opus-4-7

# 4. Same for kmm-rss-reader
skills-ab-eval run \
  --task tasks/kmm-rss-reader-agp9-migration-task \
  --skill ../kotlin-agent-skills/skills/kotlin-tooling-agp9-migration \
  --model anthropic/claude-opus-4-7
```

For statistical confidence add `--n-attempts 3` (runs each side three times and reports averages with standard deviations). Multi-trial runs are ~3× the cost and time.

## Repository layout

```
kmp-skills-eval/
├── README.md                                # this file
├── tasks/                                   # Harbor task definitions (cookbook format)
│   ├── kotlinconf-agp9-migration-task/      # Tested. Run with: skills-ab-eval run --task tasks/kotlinconf-...
│   ├── kmm-rss-reader-agp9-migration-task/  # Tested.
│   └── jetcaster-agp9-migration-task/       # Included for completeness; not part of headline results
└── results/
    ├── kotlinconf-app/
    │   ├── REPORT.md                        # Per-check breakdown + verdict
    │   ├── evaluation.json                  # Raw output of skills-ab-eval
    │   └── verifier-logs/{with,without}-skill/verifier.log
    └── kmm-rss-reader/
        └── (same shape)
```

Each `tasks/<name>/` directory follows Harbor's standard cookbook layout:
- `task.toml` — task metadata, resource budget (16 GB / 4 CPU / 100 min agent timeout), API key plumbing
- `instruction.md` — the prompt the agent receives
- `environment/Dockerfile` + `environment/scripts/` — base image with JDK, Gradle, Android SDK, and the project pre-cloned at a pinned commit
- `tests/test.sh` — the verifier (calls 5 binary checks + 3 platform build checks + tests + patch similarity)
- `tests/checks/` — Python + shell utilities: `analyze_plugins.py` (module discovery), `check_*.sh` (binary criteria), `gradle_task.sh` (build runner with `--retries`, `--wipe-cache`, `--timeout-sec`), `patch_similarity.py` (against `fix.patch`)
- `tests/fix.patch` — gold-standard migration diff (kotlinconf only; jetcaster has a placeholder; kmm-rss-reader has none and that check scores 0)

## Caveats

- **Single trial per cell.** Variance for ±0.05 around a result is plausible. The +0.700 deltas are well outside variance; the precise breakdown across binary checks is robust.
- **iOS not validated.** `xcodebuild` is macOS-only and won't run inside the Linux Docker container. The verifier explicitly skips iOS and notes this in `test.sh`.
- **Wasm/JS build uses `wasmJsBrowserDevelopmentExecutableDistribution`**, not `assemble` — the dev-dist task is the build-only half of the more familiar `BrowserDevelopmentRun` and avoids the half-extracted yarn state that `assemble` sometimes hits on cold cache. The retry path wipes `/root/.gradle/{yarn,nodejs}` between attempts as a safety net.
- **No `instruction-postfix` was used.** Agents ran with the natural prompt (`instruction.md` only) — no nudges to verify the build before declaring done. Both with- and without-skill agents would likely score higher under a postfix like "Don't stop until `./gradlew build` succeeds."

## See also

- [`JetBrains/skills-ab-eval`](https://github.com/JetBrains/skills-ab-eval) — the A/B harness
- [`Kotlin/kotlin-agent-skills`](https://github.com/Kotlin/kotlin-agent-skills) — the skill repository
- AGP 9 migration guide: [Android Multiplatform Library plugin documentation](https://developer.android.com/build/kotlin-multiplatform)
