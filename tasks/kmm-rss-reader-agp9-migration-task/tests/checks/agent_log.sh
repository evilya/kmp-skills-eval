#!/bin/bash
# Check: search an agent log for a pattern and return a binary score.
#
# Usage:
#   agent_log.sh --pattern REGEX --agent-log FILE
#
# Output: 1.0 on stdout if the pattern matches, 0.0 otherwise
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

PATTERN=""
AGENT_LOG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pattern)   PATTERN="$2";   shift 2 ;;
        --agent-log) AGENT_LOG="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

[[ -n "$PATTERN" && -n "$AGENT_LOG" ]] || {
    echo "Usage: $0 --pattern REGEX --agent-log FILE" >&2
    exit 1
}

if [ ! -f "$AGENT_LOG" ]; then
    echo "agent_log check: $AGENT_LOG not found — returning 0.0 (pattern: $PATTERN)"
    exit 1
fi

log "agent_log check: searching $AGENT_LOG (pattern: $PATTERN)"
if grep -qE "$PATTERN" "$AGENT_LOG"; then
    log "agent_log check: MATCHED"
    echo "1.0"
    exit 0
else
    log "agent_log check: NOT MATCHED"
    echo "0.0"
    exit 0
fi
