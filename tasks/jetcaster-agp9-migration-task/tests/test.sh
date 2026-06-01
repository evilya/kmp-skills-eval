#!/bin/bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p /logs/verifier

source "$SCRIPT_DIR/lib/common.sh"
log "test.sh started (pwd=$(pwd))"

BASE_COMMIT="2f9ec2d1accdb26588093ceb743701f6c6734ee4"

# --- Discover modules (project-agnostic) -----------------------------------
ANDROID_MODULE=$(python3 "$SCRIPT_DIR/checks/analyze_plugins.py" "$(pwd)" --find android-app 2>/dev/null)
DESKTOP_MODULE=$(python3 "$SCRIPT_DIR/checks/analyze_plugins.py" "$(pwd)" --find desktop-app 2>/dev/null)
log "discovered modules: android=${ANDROID_MODULE:-<none>} desktop=${DESKTOP_MODULE:-<none>}"

# --- Binary structural checks ----------------------------------------------
AGP_VERSION_SCORE=$("$SCRIPT_DIR/checks/check_agp_version.sh" --project-dir "$(pwd)")
log "AGP version score: $AGP_VERSION_SCORE"

NO_KMP_APP_SCORE=$("$SCRIPT_DIR/checks/check_no_kmp_application.sh" --project-dir "$(pwd)")
log "no-KMP+application score: $NO_KMP_APP_SCORE"

ANDROID_EXTRACTED_SCORE=$("$SCRIPT_DIR/checks/check_android_app_extracted.sh" --project-dir "$(pwd)")
log "android-app-extracted score: $ANDROID_EXTRACTED_SCORE"

BUILTIN_KOTLIN_SCORE=$("$SCRIPT_DIR/checks/check_builtin_kotlin.sh" --project-dir "$(pwd)")
log "built-in Kotlin score: $BUILTIN_KOTLIN_SCORE"

PLUGIN_MIGRATION_SCORE=$("$SCRIPT_DIR/checks/check_plugin_migration.sh" --project-dir "$(pwd)")
log "plugin-migration score: $PLUGIN_MIGRATION_SCORE"

# --- Per-platform build checks ---------------------------------------------
# Android is required; Desktop is bonus credit (skipped if module missing).
if [[ -n "$ANDROID_MODULE" ]]; then
    ANDROID_BUILD_SCORE=$("$SCRIPT_DIR/checks/gradle_task.sh" \
        --project-dir "$(pwd)" \
        --task "${ANDROID_MODULE}:assembleDebug -x spotlessCheck -x spotlessKotlinCheck" \
        --label "android_build")
else
    ANDROID_BUILD_SCORE="0.0"
    log "android build: SKIPPED (no android-app module discovered) → 0.0"
fi
log "android build score: $ANDROID_BUILD_SCORE"

if [[ -n "$DESKTOP_MODULE" ]]; then
    DESKTOP_BUILD_SCORE=$("$SCRIPT_DIR/checks/gradle_task.sh" \
        --project-dir "$(pwd)" \
        --task "${DESKTOP_MODULE}:assemble -x spotlessCheck -x spotlessKotlinCheck" \
        --label "desktop_build")
    DESKTOP_WEIGHT="0.10"
else
    DESKTOP_BUILD_SCORE="0.0"
    DESKTOP_WEIGHT="0.0"
    log "desktop build: SKIPPED (no desktop-app module discovered) → weight redistributed"
fi
log "desktop build score: $DESKTOP_BUILD_SCORE (weight=$DESKTOP_WEIGHT)"

# --- Tests (separate criterion) --------------------------------------------
if [[ -n "$ANDROID_MODULE" ]]; then
    TESTS_SCORE=$("$SCRIPT_DIR/checks/gradle_task.sh" \
        --project-dir "$(pwd)" \
        --task "${ANDROID_MODULE}:testDebugUnitTest jvmTest -x spotlessCheck -x spotlessKotlinCheck" \
        --label "tests")
else
    TESTS_SCORE="0.0"
    log "tests: SKIPPED (no android-app module) → 0.0"
fi
log "tests score: $TESTS_SCORE"

# --- Patch similarity ------------------------------------------------------
SIMILARITY_SCORE=$("$SCRIPT_DIR/checks/patch_similarity.sh" \
    --working-dir "$(pwd)" \
    --base-commit "$BASE_COMMIT" \
    --patch /tests/fix.patch)
log "patch similarity score: $SIMILARITY_SCORE"

# --- Agent process checks --------------------------------------------------
TRAJECTORY="/logs/agent/trajectory.json"

AGENT_PLANNING_SCORE=$("$SCRIPT_DIR/checks/agent_log.sh" \
    --agent-log "$TRAJECTORY" \
    --pattern '"name"\s*:\s*"TodoWrite"|TodoWrite')
log "planning score: $AGENT_PLANNING_SCORE"

AGENT_BUILD_SCORE=$("$SCRIPT_DIR/checks/agent_log.sh" \
    --agent-log "$TRAJECTORY" \
    --pattern 'gradlew.*(build|assembleRelease|assemble[A-Z])')
log "agent build score: $AGENT_BUILD_SCORE"

AGENT_TEST_SCORE=$("$SCRIPT_DIR/checks/agent_log.sh" \
    --agent-log "$TRAJECTORY" \
    --pattern 'gradlew.*(\btest\b|:check\b|\bcheck\b)')
log "agent test score: $AGENT_TEST_SCORE"

# --- Evaluation summary ----------------------------------------------------
log "scores: agp=$AGP_VERSION_SCORE no_kmp_app=$NO_KMP_APP_SCORE android_extracted=$ANDROID_EXTRACTED_SCORE builtin_kotlin=$BUILTIN_KOTLIN_SCORE plugin_migration=$PLUGIN_MIGRATION_SCORE android=$ANDROID_BUILD_SCORE desktop=$DESKTOP_BUILD_SCORE tests=$TESTS_SCORE similarity=$SIMILARITY_SCORE planning=$AGENT_PLANNING_SCORE agent_build=$AGENT_BUILD_SCORE agent_test=$AGENT_TEST_SCORE"

# Final reward — desktop weight is dynamic (0.10 if module present, 0 if not);
# unused desktop weight flows into android_build (primary build signal).
FINAL_REWARD=$(python3 -c "
desktop_w = float('$DESKTOP_WEIGHT')
android_w = 0.20 + (0.10 - desktop_w)  # absorb desktop weight when desktop absent
final = (0.10 * float('$AGP_VERSION_SCORE')
       + 0.15 * float('$NO_KMP_APP_SCORE')
       + 0.10 * float('$ANDROID_EXTRACTED_SCORE')
       + 0.05 * float('$BUILTIN_KOTLIN_SCORE')
       + 0.05 * float('$PLUGIN_MIGRATION_SCORE')
       + android_w * float('$ANDROID_BUILD_SCORE')
       + desktop_w * float('$DESKTOP_BUILD_SCORE')
       + 0.10 * float('$TESTS_SCORE')
       + 0.05 * float('$SIMILARITY_SCORE')
       + 0.0167 * float('$AGENT_PLANNING_SCORE')
       + 0.0167 * float('$AGENT_BUILD_SCORE')
       + 0.0166 * float('$AGENT_TEST_SCORE'))
print(f'{final:.4f}')
")

echo "$FINAL_REWARD" > /logs/verifier/reward.txt
log "test.sh done — final reward: $FINAL_REWARD"

exit 0
