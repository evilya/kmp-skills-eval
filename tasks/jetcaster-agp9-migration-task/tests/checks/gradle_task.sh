#!/bin/bash
# Check: run an arbitrary Gradle task list and score 1.0 on success, 0.0 on failure.
#
# Usage:
#   gradle_task.sh --project-dir DIR --task "GRADLE_ARGS" --label SHORT_NAME
#                  [--retries N] [--wipe-cache "PATH1 PATH2 ..."] [--timeout-sec N]
#
# Output: 1.0 on success (any attempt), 0.0 on failure (stdout)
# Side effect: writes /logs/verifier/gradle_<label>.log (latest attempt only)
#
# --wipe-cache PATHS: rm -rf each path between attempts (space-separated list).
#                     Useful for half-extracted toolchain dirs like /root/.gradle/yarn.
# --timeout-sec N:    kill gradle after N seconds (treat as failure for that attempt).
#                     Useful for long-running dev-server tasks.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

PROJECT_DIR=""
TASK=""
LABEL=""
RETRIES=0
WIPE_CACHE=""
TIMEOUT_SEC=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-dir) PROJECT_DIR="$2"; shift 2 ;;
        --task)        TASK="$2";        shift 2 ;;
        --label)       LABEL="$2";       shift 2 ;;
        --retries)     RETRIES="$2";     shift 2 ;;
        --wipe-cache)  WIPE_CACHE="$2";  shift 2 ;;
        --timeout-sec) TIMEOUT_SEC="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$PROJECT_DIR" || -z "$TASK" || -z "$LABEL" ]]; then
    echo "Usage: $0 --project-dir DIR --task GRADLE_ARGS --label SHORT_NAME [--retries N] [--wipe-cache 'PATHS'] [--timeout-sec N]" >&2
    exit 1
fi

LOG="/logs/verifier/gradle_${LABEL}.log"
MAX_ATTEMPTS=$((RETRIES + 1))

run_gradle_with_timeout() {
    local task="$1" log_file="$2" project_dir="$3"
    if [[ -n "$TIMEOUT_SEC" ]]; then
        (
            cd "$project_dir"
            timeout --signal=KILL "$TIMEOUT_SEC" bash -c "
                source /root/.sdkman/bin/sdkman-init.sh 2>/dev/null || true
                ./gradlew $task --no-daemon 2>&1
            "
        ) > "$log_file" 2>&1
    else
        run_gradle "$task" "$log_file" "$project_dir"
    fi
}

for ((attempt=1; attempt<=MAX_ATTEMPTS; attempt++)); do
    if (( attempt > 1 )) && [[ -n "$WIPE_CACHE" ]]; then
        log "Gradle $LABEL: wiping caches before retry: $WIPE_CACHE"
        for p in $WIPE_CACHE; do
            rm -rf "$p" 2>/dev/null || true
        done
    fi

    log "running Gradle task '$TASK' (label=$LABEL, attempt=$attempt/$MAX_ATTEMPTS, project-dir=$PROJECT_DIR)"
    if run_gradle_with_timeout "$TASK" "$LOG" "$PROJECT_DIR"; then
        log "Gradle $LABEL: SUCCEEDED (attempt $attempt)"
        echo "1.0"
        exit 0
    fi
    rc=$?
    if [[ -n "$TIMEOUT_SEC" && $rc -eq 137 ]]; then
        log "Gradle $LABEL: TIMED OUT after ${TIMEOUT_SEC}s (attempt $attempt)"
    fi
    if (( attempt < MAX_ATTEMPTS )); then
        log "Gradle $LABEL: FAILED on attempt $attempt, retrying..."
    fi
done

log "Gradle $LABEL: FAILED after $MAX_ATTEMPTS attempts"
echo "0.0"
exit 0
