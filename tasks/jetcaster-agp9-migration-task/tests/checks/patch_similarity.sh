#!/bin/bash
# Check: compare the working directory against a gold-standard state produced by
# applying PATCH to BASE_COMMIT in a temporary git worktree.
#
# Usage:
#   patch_similarity.sh --working-dir DIR --base-commit SHA --patch FILE
#
# Output: float score [0.0, 1.0] on stdout
# Exit code: always 0
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

WORKING_DIR=""
BASE_COMMIT=""
PATCH_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --working-dir) WORKING_DIR="$2"; shift 2 ;;
        --base-commit) BASE_COMMIT="$2"; shift 2 ;;
        --patch)       PATCH_FILE="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

[[ -n "$WORKING_DIR" && -n "$BASE_COMMIT" && -n "$PATCH_FILE" ]] || {
    echo "Usage: $0 --working-dir DIR --base-commit SHA --patch FILE" >&2
    exit 1
}

EXPECTED_DIR=$(mktemp -d)
log "creating gold-standard worktree at $EXPECTED_DIR (commit $BASE_COMMIT)"
git -C "$WORKING_DIR" worktree add "$EXPECTED_DIR" "$BASE_COMMIT" --detach >/dev/null 2>&1

pushd "$EXPECTED_DIR" > /dev/null
log "applying expected patch"
git apply --whitespace=nowarn "$PATCH_FILE" 2>/dev/null \
    && log "golden patch applied cleanly" \
    || log "WARNING: golden patch did not apply cleanly to the base commit"
popd > /dev/null

python3 -m pip install --target /tmp/pypackages unidiff2 >&2
export PYTHONPATH="/tmp/pypackages${PYTHONPATH:+:$PYTHONPATH}"

log "running patch_similarity.py"

SIMILARITY_LOG="/logs/verifier/patch_similarity.log"

score=$(python3 "$SCRIPT_DIR/patch_similarity.py" \
    --working-dir "$WORKING_DIR" \
    --expected-dir "$EXPECTED_DIR" \
    2> >(tee -a "$SIMILARITY_LOG" >&2))

log "patch similarity score: $score"
echo "$score"
