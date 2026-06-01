# KMM RSS Reader — KMP → AGP 9 migration

**Run date:** 2026-06-01
**Model:** `anthropic/claude-opus-4-7`
**Agent:** terminus-2 (Harbor default)
**Trials:** 1 (single A/B pair)
**Skill:** [`kotlin-tooling-agp9-migration`](https://github.com/Kotlin/kotlin-agent-skills/tree/main/skills/kotlin-tooling-agp9-migration)
**Project base commit:** `d22211507fc875849218014ad3cc09525c10247b` ([Kotlin/kmm-production-sample](https://github.com/Kotlin/kmm-production-sample))

## Headline

| | Without skill | With skill | Δ |
|---|---|---|---|
| **Reward** | **0.183** | **0.883** | **+0.700** |
| Steps | 28 | 46 | +18 |
| Tool calls | 45 | 96 | +51 |
| Cost (USD) | $0.57 | $1.73 | +$1.16 |
| Tokens | 449k | 1.82M | +1.37M |
| Skill invoked | no | yes | |
| Task marked complete by agent | yes | yes | |

**Verdict:** Skill helped meaningfully (+0.700 reward).

## Per-check breakdown

| Check | Weight | W/O | With | Notes |
|---|---|---|---|---|
| AGP version ≥ 9 | 10% | 1.0 ✓ | 1.0 ✓ | Both bumped libs.versions.toml from 8.10.1 |
| No KMP + `com.android.application` combo | 15% | **0.0** | **1.0 ✓** | Without-skill kept `:composeApp` violating the trigger |
| Android app extracted to standalone module | 10% | **0.0** | **1.0 ✓** | Without-skill never created `:androidApp` |
| Built-in Kotlin (no `org.jetbrains.kotlin.android`) | 5% | 1.0 ✓ | 1.0 ✓ | Base already satisfied (no kotlin.android plugin to remove) |
| KMP modules use new library plugin (binary) | 5% | **0.0** | **1.0 ✓** | Without-skill left old library plugin in place |
| Android `:androidApp:assembleDebug` | 20%+absorbed | **0.0** | **1.0 ✓** | Without-skill: no module to build. With-skill: passes. |
| Desktop build | 15% / redistributed | 0.0 | 0.0 | Neither created a desktop module; weight redistributed to android |
| Tests (`:androidApp:testDebugUnitTest jvmTest`) | 10% | **0.0** | **1.0 ✓** | Same cascade — no android module → tests skipped |
| Patch similarity | 5% | 0.0 | 0.0 | No `fix.patch` configured for this task; both score 0 |
| Agent ran `gradlew build` | ~1.67% | 1.0 | 1.0 | |
| Agent ran tests | ~1.67% | 1.0 | 1.0 | |
| Agent used TodoWrite | ~1.67% | 0.0 | 0.0 | |

## Where the skill made the difference

Same pattern as kotlinconf-app — the without-skill agent didn't extract a standalone Android app module from the offending `:composeApp` (which at base applies both `kotlin.multiplatform` and `com.android.application`). The skill's classification of this as a Path B scenario (mandatory restructure) is what unlocks a buildable migration:

```
discovered modules: android=<none> desktop=<none>       (without-skill)
discovered modules: android=:androidApp desktop=<none>   (with-skill)
```

Without an Android-app module, every downstream check (assembleDebug, tests) skips with score 0. With the right structural change, the same agent produces a green build that also passes unit tests.

## How to reproduce

```bash
# Prerequisites: harbor on PATH, Docker running, ANTHROPIC_API_KEY in env
cd skills-ab-eval     # the JetBrains/skills-ab-eval repo
skills-ab-eval run \
  --task ../kmp-skills-eval/tasks/kmm-rss-reader-agp9-migration-task \
  --skill ../kotlin-agent-skills/skills/kotlin-tooling-agp9-migration \
  --model anthropic/claude-opus-4-7
```

Raw verifier output: see `verifier-logs/{with,without}-skill/verifier.log`.
Raw evaluation: see `evaluation.json`.
