#!/bin/bash
# Check: Android Gradle Plugin version is >= 9.0 (the migration target).
#
# Usage: check_agp_version.sh --project-dir DIR
# Output: 1.0 if AGP major >= 9, 0.0 otherwise
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

CATALOG="$PROJECT_DIR/gradle/libs.versions.toml"
AGP_VERSION=""

if [[ -f "$CATALOG" ]]; then
    AGP_VERSION=$(python3 -c "
import re, sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore
with open('$CATALOG', 'rb') as f:
    data = tomllib.load(f)
plugins = data.get('plugins', {})
versions = data.get('versions', {})
candidates = []
for spec in plugins.values():
    if isinstance(spec, dict) and spec.get('id', '').startswith('com.android.'):
        v = spec.get('version', spec.get('version.ref'))
        if isinstance(v, dict):
            v = v.get('ref')
        if v and v in versions:
            candidates.append(versions[v])
        elif v:
            candidates.append(v)
versions_lc = {k.lower(): v for k, v in versions.items()}
for k in ['agp', 'androidgradleplugin', 'androidplugin']:
    if k in versions_lc:
        candidates.append(versions_lc[k])
for c in candidates:
    m = re.match(r'(\d+)', str(c))
    if m:
        print(m.group(1))
        sys.exit(0)
" 2>/dev/null)
fi

if [[ -z "$AGP_VERSION" ]]; then
    log "AGP version check: could not determine version"
    echo "0.0"
    exit 0
fi

if [[ "$AGP_VERSION" -ge 9 ]]; then
    log "AGP version check: PASSED (major=$AGP_VERSION >= 9)"
    echo "1.0"
else
    log "AGP version check: FAILED (major=$AGP_VERSION < 9)"
    echo "0.0"
fi
exit 0
