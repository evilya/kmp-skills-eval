#!/bin/bash
# Check: there exists at least one module applying `com.android.application`
# WITHOUT `kotlin.multiplatform`. This is the structural outcome of extracting
# the Android app from the KMP module per AGP 9 requirements.
#
# Usage: check_android_app_extracted.sh --project-dir DIR
# Output: 1.0 if such a module exists, 0.0 otherwise. Root (':') is excluded.
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

EXTRACTED=$(python3 "$SCRIPT_DIR/analyze_plugins.py" "$PROJECT_DIR" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
KMP = 'org.jetbrains.kotlin.multiplatform'
APP = 'com.android.application'
hits = [m for m, plugins in data.items() if m != ':' and APP in plugins and KMP not in plugins]
print('\n'.join(hits))
")

if [[ -n "$EXTRACTED" ]]; then
    log "android-app-extracted check: PASSED (standalone app modules: $EXTRACTED)"
    echo "1.0"
else
    log "android-app-extracted check: FAILED (no standalone com.android.application module)"
    echo "0.0"
fi
exit 0
