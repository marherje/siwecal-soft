#!/bin/bash
# Migration check: re-make a subset of the final_v9 plots with one checkout -- the frozen siwecal_k4sim ("old") or
# this repo ("new") -- on the same inputs (final_v9 + Reconstruction): final_panels (no cut, then 40 mm with the
# no-cut MIP->GeV line, 9-variable panels), position_scans on th230:E2, contained_resolution. The two output trees
# must agree (tools/validation/compare_v9_outputs.py). Batch only (v9_plots.sub): it reads a few GB from EOS.
#   run_v9_plots.sh old|new <outdir>
WHICH=${1:?old|new}; OUT=${2:?outdir}
B=/eos/experiment/drdcalo/siw-ecal/TB2026-06
GROUPS=th210_e20_26_-52,th210_e74_22_-49,th230_E2_e7.5,th230_E2_e10,th230_E2_e20,th230_E2_e34,th230_E2_e52,th230_E2_e74,th230_E4_e20,th230_E4_e74
NEW="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ "$WHICH" = old ]; then
  R=${OLD_K4SIM:?set OLD_K4SIM to the frozen siwecal_k4sim checkout (tag final-before-monorepo)}
  source "$R/init_siwecal_soft.sh" >/dev/null 2>&1
  PTS=$R/analysis/beam_points.txt
else
  R=$NEW
  source "$R/init_siwecalsoft.sh" --no-venv --quiet
  PTS=$R/simulation/campaign/beam_points.txt
fi
export MPLCONFIGDIR=${TMPDIR:-/tmp}/mpl_$USER FINAL_SIM=$B/Simulation/Processed/final_v9 FINAL_RECO=$B/Reconstruction \
       FINAL_RECO_TREES=$B/Reconstruction
for d in "$OUT" "$OUT/nocut" "$OUT/b40"; do [ -d "$d" ] || mkdir "$d"; done
cd "$R" || exit 1
set -x
python3 analysis/final_panels.py "$OUT/nocut" --groups "$GROUPS" || exit 1
python3 analysis/final_panels.py "$OUT/b40" --groups "$GROUPS" --border-cut 40 --cal-file "$OUT/nocut/mip_gev_line.txt" \
  --panels9 || exit 1
python3 analysis/position_scans.py "$OUT/b40" --scan th230:E2 --points "$PTS" --title "migration check, 40 mm" || exit 1
python3 analysis/contained_resolution.py "$OUT/b40" "$OUT/nocut" --cut 40 --margin 5 --points "$PTS" || exit 1
echo DONE
