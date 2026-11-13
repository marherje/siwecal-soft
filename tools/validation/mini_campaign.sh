#!/bin/bash
# Migration check, end to end through the new chains, on HTCondor (writes the DAGs; submits only with --submit):
#   data   3 runs (eudaq 291 = th210 20 GeV; 29 = th230 E2 74 GeV; 43 = th230 E4 20 GeV), raw -> decode -> event
#          building with calib_dir()/MuonCalib -> PID -> valtree   (data_conversion/jobs/condor/generate_reco_dag.py)
#   sim    the same 3 beam points x NEV events, ddsim through the H2-like line -> job3 (TimeOffsetNs, measured sag)
#          -> PID -> valtree                                        (simulation/campaign/make_sim_dag.py)
#   v9     tools/validation/run_v9_plots.sh old and new on final_v9 (v9_plots.sub)
# Everything is written below OUT (default Simulation/tests/monorepo_check): new folders only; raw data, the
# official calibration and the final_v9 campaign are read, never written.
#   source init_siwecalsoft.sh
#   bash tools/validation/mini_campaign.sh [--out DIR] [--nevents 5000] [--submit]
OUT=""; NEV=5000; SUBMIT=0
while [ $# -gt 0 ]; do
  case "$1" in --out) OUT="$2"; shift ;; --nevents) NEV="$2"; shift ;; --submit) SUBMIT=1 ;; *) echo "bad arg $1"; exit 2 ;; esac
  shift
done
R="${SIWECAL_SOFT_ROOT:?source init_siwecalsoft.sh}"
[ -n "$OUT" ] || OUT="$(python3 -m siwecal_common simulation_dir)/tests/monorepo_check"
W="$R/work"
for d in "$W" "$W/condor_mini_data" "$W/condor_v9_plots"; do [ -d "$d" ] || mkdir "$d"; done
# EOS: one level at a time (mkdir -p fails on the FUSE mount)
for d in "$OUT" "$OUT/data" "$OUT/data/converted" "$OUT/data/Reconstruction" "$OUT/sim" "$OUT/v9"; do
  [ -d "$d" ] || mkdir "$d" || exit 1
done

python3 "$R/data_conversion/jobs/condor/generate_reco_dag.py" \
  --runs TB2026CERN_eudaq_run_000291,TB2026CERN_run_000029,TB2026CERN_run_000043 \
  --converted-dir "$OUT/data/converted" --reco-dir "$OUT/data/Reconstruction" --out-dir "$W/condor_mini_data" || exit 1

python3 "$R/simulation/campaign/make_sim_dag.py" --campaign monorepo_check --out "$OUT/sim" \
  --dag-dir "$W/condor_mini_sim" --only th210_e20_26_-52,th230_E2_e74,th230_E4_e20 \
  --nevents "$NEV" --chunk-events 1000 || exit 1

: "${OLD_K4SIM:?set OLD_K4SIM to the frozen siwecal_k4sim checkout, for the old-vs-new v9 plots}"
cat > "$W/condor_v9_plots/v9_plots.sub" <<EOF
universe       = vanilla
environment    = "OLD_K4SIM=$OLD_K4SIM"
executable     = /bin/bash
arguments      = $R/tools/validation/run_v9_plots.sh \$(which) $OUT/v9/\$(which)
log            = $W/condor_v9_plots/v9.log
output         = $W/condor_v9_plots/\$(which).out
error          = $W/condor_v9_plots/\$(which).err
request_memory = 8000
getenv         = False
+JobFlavour    = "workday"
queue which in (old, new)
EOF

echo "DAGs and submit files written:"
echo "  condor_submit_dag $(ls "$W"/condor_mini_data/*.dag | head -1)"
echo "  condor_submit_dag $(ls "$W"/condor_mini_sim/*.dag | head -1)"
echo "  condor_submit $W/condor_v9_plots/v9_plots.sub"
if [ "$SUBMIT" = 1 ]; then
  condor_submit_dag "$(ls "$W"/condor_mini_data/*.dag | head -1)"
  condor_submit_dag "$(ls "$W"/condor_mini_sim/*.dag | head -1)"
  condor_submit "$W/condor_v9_plots/v9_plots.sub"
fi
echo "then: python3 tools/validation/compare_v9_outputs.py $OUT/v9/old $OUT/v9/new"
