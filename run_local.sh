#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Reuse the dedicated environment; never install packages or fall back to base.
if [[ "${CONDA_DEFAULT_ENV:-}" != "talent-insight" ]]; then
  if [[ -n "${CONDA_EXE:-}" && -f "$(dirname "$CONDA_EXE")/../etc/profile.d/conda.sh" ]]; then
    source "$(dirname "$CONDA_EXE")/../etc/profile.d/conda.sh"
  elif [[ -f /opt/anaconda3/etc/profile.d/conda.sh ]]; then
    source /opt/anaconda3/etc/profile.d/conda.sh
  else
    echo "Activate the existing talent-insight Conda environment first." >&2
    exit 1
  fi
  conda activate talent-insight
fi
export PATH="$CONDA_PREFIX/bin:$PATH"
exec "$CONDA_PREFIX/bin/python" "$ROOT_DIR/scripts/local_runner.py" "$@"
