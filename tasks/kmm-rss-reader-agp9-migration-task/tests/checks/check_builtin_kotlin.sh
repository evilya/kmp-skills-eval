#!/bin/bash
# Check: no module applies `org.jetbrains.kotlin.android`. AGP 9's new Android
# plugins ship with built-in Kotlin, so the explicit kotlin-android plugin must
# be removed when migrating.
#
# Usage: check_builtin_kotlin.sh --project-dir DIR
# Output: 1.0 if no module uses kotlin.android, 0.0 otherwise.
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
KA = 'org.jetbrains.kotlin.android'
offenders = [m for m, plugins in data.items() if m != ':' and KA in plugins]
print('\n'.join(offenders))
")

if [[ -z "$OFFENDERS" ]]; then
    log "builtin-kotlin check: PASSED (no module applies org.jetbrains.kotlin.android)"
    echo "1.0"
else
    log "builtin-kotlin check: FAILED (kotlin.android still applied in: $OFFENDERS)"
    echo "0.0"
fi
exit 0
