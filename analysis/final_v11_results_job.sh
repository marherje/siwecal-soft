#!/bin/bash
# Batch job: the results of final_v11 (run-by-run simulation, rectangular far collimator at 7.5-10 GeV) for the
# summary report, into <out>/{nocut,b<cut>,ref_v9,run_shapes.tsv}. Same chain as final_v9_plots_job.sh, with the
# simulation read per run (final_panels.sim_valtrees, final_profiles.sim_files) and pooled per group of beam_points.txt:
#   nocut          final_panels.py without the border cut: MIP -> GeV lines (mip_gev_line.txt), panels per group,
#                  final_panels_summary.txt (sigma/mu and sim/data per group), resolution_vs_energy.png
#   b<cut>         final_panels.py --border-cut with its own MIP -> GeV line, fitted on the cut scans (b<cut>/
#                  mip_gev_line.txt, read by the next steps), summarized panels (final_panels_select.py) and longitudinal
#                  profiles (final_profiles.py) of four reference groups, contained_resolution.py, position_scans.py
#                  (linearity and resolution of the th230 position scans; SCAN_EXCLUDE_<cut>: groups left out of them,
#                  default th230_E1_e74 at 50 mm, where the cut keeps only the tail of that beam)
#   run_shapes.tsv run_shapes.py: beam spot and shower shapes run by run, final_v11 against final_v9 (REF)
#   ref_v9         final_panels.py on final_v9 without the cut: the previous campaign's numbers, same code (SKIP_REF=1:
#                  not done)
# Writes nothing outside <out>; refuses an existing <out>/run_shapes.tsv.
#   CACHE_FROM=<earlier out>  copy its per-group event caches (same selection) instead of re-reading every valtree
#   DATA, DATA_TREES          data valtrees and ecal trees (default Reconstruction); both, for a re-reconstructed data set
#   SKIP_SHAPES=1             no run_shapes.tsv (it does not depend on the calibration)
# Test while the campaign runs (default: neither, every group and the line fitted on the scans):
#   ONLY_GROUPS=g1,g2,...  final_panels.py on those groups only; needs CAL_FILE (the scans are incomplete)
#   CAL_FILE=<mip_gev_line.txt>  the MIP -> GeV line, read instead of fitted (every pass)
#
#   bash analysis/final_v11_results_job.sh <out>          (on HTCondor: it reads every data and simulation valtree)
OUT=${1:?out}
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
B=/eos/experiment/drdcalo/siw-ecal/TB2026-06
DATA=${DATA:-$B/Reconstruction}
SIM=${SIM:-$B/Simulation/Processed/final_v11}
REF=${REF:-$B/Simulation/Processed/final_v9}
CUTS=${CUTS:-50}
SCAN_EXCLUDE_50=${SCAN_EXCLUDE_50-th230_E1_e74}
PANEL_GROUPS=${PANEL_GROUPS:-th210_e20_26_-52,th210_e74_22_-49,th230_E4_e20,th230_E4_e74}   # not GROUPS: bash's own
ONLY=${ONLY_GROUPS:+--groups $ONLY_GROUPS}
CAL0=${CAL_FILE:+--cal-file $CAL_FILE}
source "$R/init_siwecalsoft.sh" --no-venv --quiet
export MPLCONFIGDIR=${TMPDIR:-/tmp}/mpl_$USER
cd "$R" || exit 1
for d in "$OUT" "$OUT/nocut"; do [ -d "$d" ] || mkdir "$d"; done
step() { echo "=== $*"; "$@" || { echo "FAILED: $*"; exit 1; }; }
caches() {   # caches() <subdir>: the event caches of CACHE_FROM/<subdir>, copied once (cp -n: nothing overwritten)
  [ -n "$CACHE_FROM" ] && [ -d "$CACHE_FROM/$1" ] || return 0
  local cache   # not c: the loop over the cuts uses it
  for cache in "$CACHE_FROM/$1"/cache_*; do [ -d "$cache" ] && cp -rn "$cache" "$OUT/$1/"; done; return 0
}

export FINAL_SIM=$SIM FINAL_RECO=$DATA FINAL_RECO_TREES=${DATA_TREES:-$B/Reconstruction}   # data ecal trees of the profiles
caches nocut
step python3 analysis/final_panels.py "$OUT/nocut" $ONLY $CAL0
for c in $CUTS; do
  D=$OUT/b$c; [ -d "$D" ] || mkdir "$D"
  caches "b$c"
  step python3 analysis/final_panels.py "$D" --border-cut "$c" $ONLY $CAL0   # MIP -> GeV line fitted on the cut scans
  CAL=$D/mip_gev_line.txt
  for g in ${PANEL_GROUPS//,/ }; do
    step python3 analysis/final_panels_select.py "$D" --group "$g" --border-cut "$c" --cal-file "$CAL"
  done
  step python3 analysis/final_profiles.py "$D" --groups "$PANEL_GROUPS" --border-cut "$c" --cal-file "$CAL"
  step python3 analysis/contained_resolution.py "$D" "$OUT/nocut" --cut "$c" --margin 5
  ex_var=SCAN_EXCLUDE_$c
  step python3 analysis/position_scans.py "$D" --exclude "${!ex_var}" \
    --title "shower-like events, barxy_min_border_distance > $c mm, final_v11${!ex_var:+; left out: ${!ex_var}}"
done
[ "${SKIP_SHAPES:-0}" = 1 ] || step python3 analysis/run_shapes.py "$SIM" --ref "$REF" --out "$OUT/run_shapes.tsv"
if [ "${SKIP_REF:-0}" != 1 ]; then
  [ -d "$OUT/ref_v9" ] || mkdir "$OUT/ref_v9"
  FINAL_SIM=$REF step python3 analysis/final_panels.py "$OUT/ref_v9" $ONLY $CAL0
fi
echo "DONE"
