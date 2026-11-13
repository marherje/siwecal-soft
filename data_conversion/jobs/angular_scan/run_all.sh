#!/bin/bash
# Event-build + validate every run of runs.yml, sequentially (steer_eventbuild.py, validate.py with ANGSCAN_RUN).
# Idempotent: a run whose ecal_<RUN>.edm4hep.root exists is skipped, unless --force. Needs init_siwecalsoft.sh.
#   bash data_conversion/jobs/angular_scan/run_all.sh [--force]
set -eo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FORCE=0; [ "$1" = "--force" ] && FORCE=1
CONVERTED="$(python3 -m siwecal_common converted_dir)"
N=0
for NUM in $(python3 -c "import yaml; print(' '.join(map(str, yaml.safe_load(open('$HERE/runs.yml'))['runs'])))"); do
  RUN=$(printf "TB2026CERN_eudaq_run_%06d" "$NUM")
  EDM4HEP="$CONVERTED/$RUN/events/ecal_${RUN}.edm4hep.root"
  if [ "$FORCE" != "1" ] && [ -s "$EDM4HEP" ]; then
    echo "[angular_scan] $RUN: already done -> $EDM4HEP (skip; use --force to redo)"; continue
  fi
  echo "[angular_scan] $RUN: event builder"
  ANGSCAN_RUN=$NUM k4run "$HERE/steer_eventbuild.py"
  echo "[angular_scan] $RUN: validation (EDM4hep/PID)"
  ANGSCAN_RUN=$NUM k4run "$HERE/validate.py"
  N=$((N+1))
done
echo "[angular_scan] $N run(s) processed."
