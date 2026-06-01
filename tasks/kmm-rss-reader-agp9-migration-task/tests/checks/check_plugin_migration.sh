#!/bin/bash
# Check: among KMP modules that apply any Android plugin, do *all* of them use
# the AGP-9-native `com.android.kotlin.multiplatform.library` (binary)?
#
# Usage: check_plugin_migration.sh --project-dir DIR
# Output: 1.0 if every KMP+Android module uses the new plugin and none use the
#         old `com.android.library`; 0.0 otherwise. 1.0 if no KMP+Android
#         modules exist (nothing to migrate).
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

read SCORE NEW OLD < <(python3 "$SCRIPT_DIR/analyze_plugins.py" "$PROJECT_DIR" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
KMP = 'org.jetbrains.kotlin.multiplatform'
OLD = 'com.android.library'
NEW = 'com.android.kotlin.multiplatform.library'
APP = 'com.android.application'
kmp_android = [m for m, plugins in data.items()
               if m != ':' and KMP in plugins and (OLD in plugins or NEW in plugins or APP in plugins)]
new_count = sum(1 for m in kmp_android if NEW in data[m])
old_count = sum(1 for m in kmp_android if OLD in data[m] and NEW not in data[m])
if not kmp_android:
    print('1.0 0 0')
elif new_count == len(kmp_android) and old_count == 0:
    print(f'1.0 {new_count} {old_count}')
else:
    print(f'0.0 {new_count} {old_count}')
")

log "plugin-migration check: new=$NEW, old=$OLD → score=$SCORE (binary)"
echo "$SCORE"
exit 0
