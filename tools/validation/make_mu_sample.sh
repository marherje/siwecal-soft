#!/bin/bash
# The local muon sample the simulation unit tests read (analysis/tests: channel mapper, detector flipper, converter,
# PID output), in work/mu_beam (git-ignored) or SIWECAL_MU_SAMPLE_DIR. It used to come from the retired
# gaudi_jobs/1_mu_beam_pipeline; now it is the campaign chain on one muon point:
#   ddsim (simulation/run/ddsim_beam_chunk.sh, th230 muon point of muon_points.txt, H2-like line)
#   -> job3_digitize.py DIGI_MODE=both (SiPadHitsDigi/Flipped/Mapped/Masked + the real chain) -> digitized.edm4hep.root
#   -> simulation/campaign/run_pid_sim.sh (ecal_sim.root, ecal_sim.edm4hep.root, ecal_sim.valtree.root)
# Batch job (make_mu_sample.sub), ~N=2000 events:  condor_submit tools/validation/make_mu_sample.sub
#   bash tools/validation/make_mu_sample.sh [N]
N=${1:-2000}
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT=${SIWECAL_MU_SAMPLE_DIR:-$R/work/mu_beam}
for d in "$R/work" "$OUT"; do [ -d "$d" ] || mkdir "$d"; done
W=$(mktemp -d "${TMPDIR:-/tmp}/mu_sample_XXXX")
cd "$W" || exit 1
source "$R/init_siwecalsoft.sh" --no-venv --quiet || exit 1
# th230_mu150_-4_7: 150 GeV mu-, centre (-4, 7) mm, sigma (36.5, 39.0) mm
COMPACT_FILE=SND_compact_beamline.xml BEAM_Z_MM=-65500 PHYSICS_LIST=QGSP_BERT_EMZ KEEP_LOCAL=1 \
  bash "$R/simulation/run/ddsim_beam_chunk.sh" "$R" "$N" mu- 150 -4 7 36.5 39.0 0.02 31337 - || exit 1
CALIB_THRESHOLD=th230 DIGI_MODE=both INPUT_FILE="$W/sim.edm4hep.root" BEAM_Z_MM=-65500 ECAL_TREE_OUTPUT=ecal_sim.root \
  k4run "$R/simulation/jobs/job3_digitize.py" > job3.log 2>&1 || { tail -20 job3.log; exit 1; }
cp digitized.edm4hep.root ecal_sim.root ecal_sim_simple.root "$OUT/" || exit 1
(cd "$OUT" && bash "$R/simulation/campaign/run_pid_sim.sh" --format both) || exit 1
rm -rf "$W"
echo "DONE: $(ls "$OUT")"
