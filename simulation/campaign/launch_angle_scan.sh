#!/bin/bash
# Run-by-run simulation and reconstruction of the angular scan (runs_angle.txt: positrons at 5, 10 and 30 deg,
# 7.5-74 GeV, th210; 150 GeV muons at 45 deg, th210/220/230, for tracking),
# as final_v11 but with the ECAL turned about y: per angle, the turned geometry (angle_geometry.py) and one DAG of
# make_run_sim_dag.py (beam spot measured on each run's data valtree, dummy + tune, chunks, PID + valtree, closure;
# rectangular far collimator at 7.5 and 10 GeV), all writing to Simulation/Processed/<CAMPAIGN>/.
#
#   bash simulation/campaign/launch_angle_scan.sh            # writes one DAG per angle (nothing on EOS)
#   bash simulation/campaign/launch_angle_scan.sh --submit   # ... and submits them
#   any other option goes to make_run_sim_dag.py, e.g. a test on one run:
#   CAMPAIGN=test_angle ANGLES=30 bash simulation/campaign/launch_angle_scan.sh --only TB2026CERN_eudaq_run_000212 \
#       --dummy-events 500 --max-events 1000 --chunk-events 500 --submit
#
# Environment:
#   CAMPAIGN       output Simulation/Processed/<CAMPAIGN> (default angle_v1); DAGs in work/condor_<CAMPAIGN>_a<angle>/
#   DATA_RECO      data area with <RUN>/ecal_<RUN>.valtree.root of the angle runs (default: Reconstruction)
#   ANGLES         angles to launch (default "5 10 30 45"; 45 = the muon runs)
#   ANGLE_SIGN     1 or -1: direction of the turn about y (default 1)
#   ALLOW_MISSING  1: launch the runs whose data valtree exists (default: stop if one is missing)
# Seeds: --seed-offset 40000000 + angle * 100000 (no seed shared with final_v11 or between angles).
# When every DAG has finished: python3 simulation/campaign/campaign_summary.py <out> simulation/campaign/runs_angle.txt
# No set -e / set -u: key4hep's setup does not survive them.
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CAMPAIGN=${CAMPAIGN:-angle_v1}
ANGLES=${ANGLES:-5 10 30 45}
SIGN=${ANGLE_SIGN:-1}
LIST=$R/simulation/campaign/runs_angle.txt
case "$SIGN" in 1|-1) ;; *) echo "ERROR: ANGLE_SIGN must be 1 or -1" >&2; exit 1 ;; esac

source "$R/init_siwecalsoft.sh" --no-venv --quiet || { echo "ERROR: init_siwecalsoft.sh failed" >&2; exit 1; }
RECO=${DATA_RECO:-$(python3 -c 'from siwecal_common import paths; print(paths.reconstruction_dir())')} || exit 1

missing=""
for run in $(awk -v angles=" $ANGLES " '!/^#/ && NF >= 6 && index(angles, " " $6 " ") {print $1}' "$LIST"); do
  [ -f "$RECO/$run/ecal_$run.valtree.root" ] || missing="$missing $run"
done
if [ -n "$missing" ]; then
  echo "No data valtree in $RECO for:$missing" >&2
  [ "${ALLOW_MISSING:-0}" = 1 ] || { echo "ERROR: reconstruct the angle runs first (or DATA_RECO=..., ALLOW_MISSING=1)" >&2; exit 1; }
fi

for A in $ANGLES; do
  D=$R/work/condor_${CAMPAIGN}_a$A
  mkdir -p "$D"
  awk -v a="$A" '!/^#/ && NF >= 6 && $6 == a' "$LIST" > "$D/runs_a$A.txt"
  [ -s "$D/runs_a$A.txt" ] || { echo "ERROR: no run at $A deg in $LIST" >&2; exit 1; }
  git -C "$R" rev-parse HEAD > "$D/launched_from.txt"
  git -C "$R" diff HEAD > "$D/uncommitted.diff"
  COMPACT=$(python3 "$R/simulation/campaign/angle_geometry.py" "$CAMPAIGN" "$((SIGN * A))") || exit 1
  echo "=== $A deg: $COMPACT"
  python3 "$R/simulation/campaign/make_run_sim_dag.py" --campaign "$CAMPAIGN" --runs "$D/runs_a$A.txt" --dag-dir "$D" \
    --compact "$COMPACT" --rect-collimator 7.5,10 --seed-offset $((40000000 + A * 100000)) --no-summary \
    --data-reco "$RECO" "$@" || { echo "ERROR: make_run_sim_dag.py failed at $A deg" >&2; exit 1; }
done
echo "When every DAG has finished: python3 $R/simulation/campaign/campaign_summary.py" \
     "<out: Simulation/Processed/$CAMPAIGN> $LIST"
