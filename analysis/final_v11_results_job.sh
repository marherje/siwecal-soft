#!/bin/bash
# Batch job: the results of final_v11 (run-by-run simulation, rectangular far collimator at 7.5-10 GeV) for the
# summary report, into <out>/{nocut,b<cut>,ref_v9,run_shapes.tsv}. Same chain as final_v9_plots_job.sh, with the
# simulation read per run (final_panels.sim_valtrees, final_profiles.sim_files) and pooled per group of beam_points.txt:
#   nocut          final_panels.py without the border cut: MIP -> GeV lines (mip_gev_line.txt), panels per group,
#                  final_panels_summary.txt (sigma/mu and sim/data per group), resolution_vs_energy.png
#   b<cut>         final_panels.py --border-cut, summarized panels (final_panels_select.py) and longitudinal profiles
#                  (final_profiles.py) of four reference groups, contained_resolution.py, position_scans.py
#                  (linearity and resolution of the th230 position scans)
#   run_shapes.tsv run_shapes.py: beam spot and shower shapes run by run, final_v11 against final_v9 (REF)
#   ref_v9         final_panels.py on final_v9 without the cut: the previous campaign's numbers, same code (SKIP_REF=1:
#                  not done)
# Writes nothing outside <out>; refuses an existing <out>/run_shapes.tsv.
# ONLY_GROUPS=g1,g2,...: final_panels.py on those groups only (a test while the campaign runs; default: all groups).
#
#   bash analysis/final_v11_results_job.sh <out>          (on HTCondor: it reads every data and simulation valtree)
OUT=${1:?out}
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
B=/eos/experiment/drdcalo/siw-ecal/TB2026-06
DATA=${DATA:-$B/Reconstruction}
SIM=${SIM:-$B/Simulation/Processed/final_v11}
REF=${REF:-$B/Simulation/Processed/final_v9}
CUTS=${CUTS:-50}
PANEL_GROUPS=${PANEL_GROUPS:-th210_e20_26_-52,th210_e74_22_-49,th230_E4_e20,th230_E4_e74}   # not GROUPS: bash's own
ONLY=${ONLY_GROUPS:+--groups $ONLY_GROUPS}
source "$R/init_siwecalsoft.sh" --no-venv --quiet
export MPLCONFIGDIR=${TMPDIR:-/tmp}/mpl_$USER
cd "$R" || exit 1
for d in "$OUT" "$OUT/nocut"; do [ -d "$d" ] || mkdir "$d"; done
step() { echo "=== $*"; "$@" || { echo "FAILED: $*"; exit 1; }; }

export FINAL_SIM=$SIM FINAL_RECO=$DATA FINAL_RECO_TREES=$B/Reconstruction
step python3 analysis/final_panels.py "$OUT/nocut" $ONLY
CAL=$OUT/nocut/mip_gev_line.txt
for c in $CUTS; do
  D=$OUT/b$c; [ -d "$D" ] || mkdir "$D"
  step python3 analysis/final_panels.py "$D" --border-cut "$c" --cal-file "$CAL" $ONLY
  for g in ${PANEL_GROUPS//,/ }; do
    step python3 analysis/final_panels_select.py "$D" --group "$g" --border-cut "$c" --cal-file "$CAL"
  done
  step python3 analysis/final_profiles.py "$D" --groups "$PANEL_GROUPS" --border-cut "$c" --cal-file "$CAL"
  step python3 analysis/contained_resolution.py "$D" "$OUT/nocut" --cut "$c" --margin 5
  step python3 analysis/position_scans.py "$D" --title "shower-like events, barxy_min_border_distance > $c mm, final_v11"
done
step python3 analysis/run_shapes.py "$SIM" --ref "$REF" --out "$OUT/run_shapes.tsv"
if [ "${SKIP_REF:-0}" != 1 ]; then
  [ -d "$OUT/ref_v9" ] || mkdir "$OUT/ref_v9"
  FINAL_SIM=$REF step python3 analysis/final_panels.py "$OUT/ref_v9" $ONLY
fi
echo "DONE"
