#!/bin/bash
# Shared utilities for verifier check scripts. Source this file; do not execute it directly.

LOG_FILE="${LOG_FILE:-/logs/verifier/verifier.log}"

log() {
    local msg="[$(date -Iseconds)] $*"
    echo "$msg" >&2
    echo "$msg" >> "$LOG_FILE"
}

# run_gradle TASK LOG_FILE [PROJECT_DIR]
# Runs ./gradlew TASK inside PROJECT_DIR (defaults to cwd), capturing all output to LOG_FILE.
# Returns the exit code of gradlew.
run_gradle() {
    local task="$1"
    local log_file="$2"
    local project_dir="${3:-.}"
    (
        cd "$project_dir"
        bash -c "
            source /root/.sdkman/bin/sdkman-init.sh 2>/dev/null || true
            ./gradlew $task --no-daemon 2>&1
        "
    ) > "$log_file" 2>&1
}
