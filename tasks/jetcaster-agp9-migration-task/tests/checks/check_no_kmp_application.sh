#!/bin/bash
# Check: no module combines `kotlin.multiplatform` with `com.android.application`.
# This is the AGP 9 trigger condition the migration is meant to resolve.
#
# Usage: check_no_kmp_application.sh --project-dir DIR
# Output: 1.0 if no module combines them, 0.0 otherwise. Root (':') is excluded.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

PROJECT_DIR=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --project-dir) PROJECT_DIR="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done
[[ -n "$PROJECT_DIR" ]] || { echo "Usage: $0 --project-dir DIR" >&2; exit 1; }

OFFENDERS=$(python3 "$SCRIPT_DIR/analyze_plugins.py" "$PROJECT_DIR" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
KMP = 'org.jetbrains.kotlin.multiplatform'
APP = 'com.android.application'
offenders = [m for m, plugins in data.items() if m != ':' and KMP in plugins and APP in plugins]
print('\n'.join(offenders))
")

if [[ -z "$OFFENDERS" ]]; then
    log "no-KMP-application check: PASSED (no module combines KMP + com.android.application)"
    echo "1.0"
else
    log "no-KMP-application check: FAILED (offenders: $OFFENDERS)"
    echo "0.0"
fi
exit 0
