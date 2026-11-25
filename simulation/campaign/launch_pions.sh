#!/bin/bash
# Pion samples (docs/sim/pion_samples.md): the pion runs of the test beam and the pion background at E2.
#
#   bash simulation/campaign/launch_pions.sh reco [--submit]   event building + PID of the pion data runs (runs_pion.txt)
#   bash simulation/campaign/launch_pions.sh valtree           their valtrees, when the reco DAG has finished
#   bash simulation/campaign/launch_pions.sh runs [--submit]   simulation of those runs (make_run_sim_dag.py, beam spot and
#                                                              statistics of each run); needs the valtrees
#   bash simulation/campaign/launch_pions.sh e2   [--submit]   E2 background, one file per energy (pion_points.txt,
#                                                              make_sim_dag.py); independent of the data
# Without --submit the DAGs are only written (reco also creates the empty run folders in DATA_RECO). Any other option of
# runs / e2 goes to the DAG writer, e.g. a test:
#   E2_CAMPAIGN=test_pion bash simulation/campaign/launch_pions.sh e2 --only th230_E2_pi_e10 --nevents 20 --chunk-events 10
#
# Environment:
#   DATA_RECO                  reconstruction area, read and written (default: Reconstruction)
#   RUNS_CAMPAIGN, E2_CAMPAIGN campaign names (default pion_data_v1, pion_E2_v1); --out <dir> for another place
#   NEVENTS                    events per E2 energy (default 50000)
#   RUNS_SEED, E2_SEED         seed offsets (default 70000000, 80000000); a new one for more statistics
#   MIN_EVENTS                 runs with fewer data events are skipped (default 1000)
# No set -e / set -u: key4hep's setup does not survive them.
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIST=$R/simulation/campaign/runs_pion.txt
MODE=${1:-}
case "$MODE" in reco|valtree|runs|e2) shift ;; *) echo "usage: launch_pions.sh reco|valtree|runs|e2 [options]" >&2; exit 1 ;; esac
source "$R/init_siwecalsoft.sh" --no-venv --quiet || { echo "ERROR: init_siwecalsoft.sh failed" >&2; exit 1; }
RECO=${DATA_RECO:-$(python3 -c 'from siwecal_common import paths; print(paths.reconstruction_dir())')} || exit 1
RUNS=$(awk '!/^#/ && NF >= 5 {print $1}' "$LIST")
cd "$R" || exit 1

missing() {   # missing <suffix>: the runs without <RECO>/<RUN>/ecal_<RUN><suffix>
  local run
  for run in $RUNS; do [ -s "$RECO/$run/ecal_$run$1" ] || echo "$run"; done
}

case "$MODE" in
reco)
  case "$#:${1:-}" in 0:|1:--submit) ;; *) echo "ERROR: reco takes only --submit" >&2; exit 1 ;; esac
  for run in $RUNS; do
    [ ! -e "$RECO/$run/ecal_$run.root" ] || { echo "ERROR: $RECO/$run/ecal_$run.root exists, not redone" >&2; exit 1; }
  done
  D=$R/work/condor_reco_pions_$(date +%Y%m%d_%H%M%S)   # a new folder per call
  python3 data_conversion/jobs/condor/generate_reco_dag.py --no-validation --reco-dir "$RECO" \
    --runs "$(echo $RUNS | tr ' ' ',')" --out-dir "$D" || exit 1
  # These runs were decoded from LCIO into one chunk_0000.root. The generator lists every raw .bin file, and CONVERT
  # would write chunk_0001... into the shared decoded data: its nodes are DONE from the start.
  sed -i 's/^JOB convert_.*/& DONE/' "$D/reco.dag"
  n=$(echo $RUNS | wc -w)
  if [ "$(grep -c '^JOB convert_' "$D/reco.dag")" != "$n" ] || [ "$(grep -c '^JOB convert_.* DONE$' "$D/reco.dag")" != "$n" ]; then
    echo "ERROR: CONVERT nodes not marked DONE, do NOT submit $D/reco.dag" >&2; exit 1
  fi
  echo "CONVERT nodes DONE ($n); DAG: $D/reco.dag"
  [ "${1:-}" != --submit ] || condor_submit_dag "$D/reco.dag"
  ;;
valtree)
  m=$(missing .edm4hep.root)
  [ -z "$m" ] || { echo "ERROR: not reconstructed in $RECO:" $m >&2; exit 1; }
  for run in $(missing .valtree.root); do
    python3 reconstruction/jobs/pid_to_valtree.py "$RECO/$run/ecal_$run.edm4hep.root" || exit 1
  done
  ;;
runs)
  m=$(missing .valtree.root)
  [ -z "$m" ] || { echo "ERROR: no data valtree in $RECO (reco, valtree first):" $m >&2; exit 1; }
  python3 simulation/campaign/make_run_sim_dag.py --campaign "${RUNS_CAMPAIGN:-pion_data_v1}" --runs "$LIST" \
    --data-reco "$RECO" --seed-offset "${RUNS_SEED:-70000000}" --min-events "${MIN_EVENTS:-1000}" "$@"
  ;;
e2)
  python3 simulation/campaign/make_sim_dag.py --campaign "${E2_CAMPAIGN:-pion_E2_v1}" \
    --points "$R/simulation/campaign/pion_points.txt" --nevents "${NEVENTS:-50000}" \
    --seed-offset "${E2_SEED:-80000000}" "$@"
  ;;
esac
