#!/usr/bin/env bash
#
# Run black --check and pylint against Python in this project, using the
# ctsm_pylib conda environment and the CTSM-standard config files:
#
#   - black:  $REPO_ROOT/python/pyproject.toml
#   - pylint: $REPO_ROOT/python/ctsm/.pylintrc  (-j 4)
#
# Usage:
#   .claude/namelist-testing-modernization/scripts/check_python.sh
#       # default target: bld/unit_testers_python/
#   .claude/namelist-testing-modernization/scripts/check_python.sh <path> [<path> ...]
#
# Intended to be run before every commit that touches Python code under
# bld/unit_testers_python/ (or any other Python this project adds). Exits
# non-zero on the first violation; stdout/stderr are streamed live so a
# failed black/pylint run is visible in real time.
#
# Reproduce its effect manually with:
#   conda activate ctsm_pylib
#   black  --check --config python/pyproject.toml   <paths>
#   pylint        --rcfile python/ctsm/.pylintrc -j 4 <paths>

set -euo pipefail

# Resolve repo root via git (robust to script-location changes); fall back
# to a relative path computed from this script's location.
if REPO_ROOT="$(git -C "$(dirname -- "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)"; then
    :
else
    SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
    REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
fi

# Determine paths to check.
if [ "$#" -eq 0 ]; then
    PATHS=( "$REPO_ROOT/bld/unit_testers_python" )
else
    PATHS=( "$@" )
fi

# Drop nonexistent paths with a note. This lets the script be invoked
# before bld/unit_testers_python/ has been created (e.g., pre-PR1).
EXISTING=()
for p in "${PATHS[@]}"; do
    if [ -e "$p" ]; then
        EXISTING+=( "$p" )
    else
        echo "Note: path does not exist (skipping): $p"
    fi
done

if [ "${#EXISTING[@]}" -eq 0 ]; then
    echo "No paths to check. Nothing to do."
    exit 0
fi

# Ensure ctsm_pylib is active. If we are already in it, skip activation;
# otherwise source conda's init and activate.
if [ "${CONDA_DEFAULT_ENV:-}" != "ctsm_pylib" ]; then
    if ! command -v conda >/dev/null 2>&1; then
        echo "ERROR: 'conda' is not on PATH." >&2
        echo "       Activate ctsm_pylib first, or initialize conda for this shell" >&2
        echo "       (e.g. 'module load conda' on Derecho), then re-run." >&2
        exit 1
    fi
    CONDA_BASE="$(conda info --base 2>/dev/null)"
    if [ -z "$CONDA_BASE" ] || [ ! -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
        echo "ERROR: could not locate conda.sh under conda base ($CONDA_BASE)." >&2
        exit 1
    fi
    # shellcheck disable=SC1091
    source "$CONDA_BASE/etc/profile.d/conda.sh"
    conda activate ctsm_pylib
fi

BLACK_CONFIG="$REPO_ROOT/python/pyproject.toml"
PYLINT_RCFILE="$REPO_ROOT/python/ctsm/.pylintrc"

if [ ! -f "$BLACK_CONFIG" ];   then echo "ERROR: missing $BLACK_CONFIG"   >&2; exit 1; fi
if [ ! -f "$PYLINT_RCFILE" ];  then echo "ERROR: missing $PYLINT_RCFILE"  >&2; exit 1; fi

echo "==> black --check --config $BLACK_CONFIG ${EXISTING[*]}"
black --check --config "$BLACK_CONFIG" "${EXISTING[@]}"

echo "==> pylint --rcfile $PYLINT_RCFILE -j 4 ${EXISTING[*]}"
pylint --rcfile "$PYLINT_RCFILE" -j 4 "${EXISTING[@]}"

echo "==> All Python checks passed."
