# KotlinConf-app — KMP → AGP 9 migration

**Run date:** 2026-06-01
**Model:** `anthropic/claude-opus-4-7`
**Agent:** terminus-2 (Harbor default)
**Trials:** 1 (single A/B pair)
**Skill:** [`kotlin-tooling-agp9-migration`](https://github.com/Kotlin/kotlin-agent-skills/tree/main/skills/kotlin-tooling-agp9-migration)
**Project base commit:** `4c5b079cc4df8205ab390036f45987e13ebac32c` ([JetBrains/kotlinconf-app](https://github.com/JetBrains/kotlinconf-app))

## Headline

| | Without skill | With skill | Δ |
|---|---|---|---|
| **Reward** | **0.224** | **0.965** | **+0.740** |
| Steps | 20 | 37 | +17 |
| Tool calls | 28 | 55 | +27 |
| Cost (USD) | $0.39 | $1.17 | +$0.78 |
| Tokens | 304k | 1.16M | +857k |
| Skill invoked | no | yes | |
| Task marked complete by agent | yes | yes | |

**Verdict:** Skill helped meaningfully (+0.740 reward).

## Per-check breakdown

| Check | Weight | W/O | With | Notes |
|---|---|---|---|---|
| AGP version ≥ 9 | 10% | 1.0 ✓ | 1.0 ✓ | Both bumped libs.versions.toml |
| No KMP + `com.android.application` combo | 15% | **0.0** | **1.0 ✓** | Without-skill kept `:androidApp` violating the trigger condition |
| Android app extracted to standalone module | 10% | **0.0** | **1.0 ✓** | Without-skill never extracted a standalone Android app |
| Built-in Kotlin (no `org.jetbrains.kotlin.android`) | 5% | 1.0 ✓ | 1.0 ✓ | Both removed the kotlin.android plugin |
| KMP modules use new library plugin (binary) | 5% | **0.0** | **1.0 ✓** | Without-skill left some libs on `com.android.library` |
| Android `:androidApp:assembleDebug` | 20%+absorbed | **0.0** | **1.0 ✓** | Without-skill: broken state. With-skill: passes. |
| Desktop build | 10% / redistributed | 0.0 | 0.0 | Neither produced a desktop module; weight redistributed to android |
| Web build | 5% / redistributed | 0.0 | 0.0 | Same |
| Tests (`:androidApp:testDebugUnitTest jvmTest`) | 10% | **0.0** | **1.0 ✓** | Same cascade — build broken → tests skipped |
| Patch similarity vs `fix.patch` | 5% | 0.82 | 0.96 | Both surprisingly close to gold textually |
| Agent ran `gradlew build` | ~1.67% | 1.0 | 1.0 | |
| Agent ran tests | ~1.67% | 1.0 | 0.0 | |
| Agent used TodoWrite | ~1.67% | 0.0 | 0.0 | terminus-2 doesn't use this pattern |

## Where the skill made the difference

The without-skill agent **didn't know about the AGP 9 trigger condition** — it tried to migrate the KMP + `com.android.application` combination in-place rather than extract a standalone Android app. The skill explicitly teaches:

> "Path B is **mandatory** for any module combining KMP + Android application plugin"

Without that knowledge, the agent took a structurally invalid path that produces no working build. With the skill, it correctly performs the Path B extraction and produces a green build + green tests.

The patch_similarity check (0.82 vs 0.96) shows both agents edited similar files — but only the with-skill agent reached a build-passing state. The structural binary checks (`no_kmp_app`, `android_extracted`, `plugin_migration`) — which are 30 percentage points of the rubric — are exactly the dimensions where the skill's Path-classification guidance is decisive.

## How to reproduce

```bash
# Prerequisites: harbor on PATH, Docker running, ANTHROPIC_API_KEY in env
cd skills-ab-eval     # the JetBrains/skills-ab-eval repo
skills-ab-eval run \
  --task ../kmp-skills-eval/tasks/kotlinconf-agp9-migration-task \
  --skill ../kotlin-agent-skills/skills/kotlin-tooling-agp9-migration \
  --model anthropic/claude-opus-4-7
```

Raw verifier output: see `verifier-logs/{with,without}-skill/verifier.log`.
Raw evaluation: see `evaluation.json`.
