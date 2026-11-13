#!/bin/bash
# Dummy pass of one run (node d_<RUN> of simulation/campaign/make_run_sim_dag.py): simulate the run with the initial gun
# (data centre and width, params/<RUN>.data.json), measure the simulated spot and tune the gun -> params/<RUN>.json,
# which the production chunks read. All event-level computation is C++ (ddsim, job3, the PID job, siwecal_beamspot).
#
#   run_sim_dummy.sh <repo> <campaign_dir> <RUN> <seed> <dummy_events>
#   in : <campaign_dir>/params/<RUN>.data.json
#   out: <campaign_dir>/params/<RUN>.json, <campaign_dir>/dummy/<RUN>/ecal_dummy_<RUN>{,_simple}.root (+ .valtree.root)
# Environment (from the .sub): COMPACT_FILE, BEAM_Z_MM, PHYSICS_LIST, RECO_TABLE, SIGMA_E (default 0.02).
# No set -e / set -u: key4hep's setup and k4run do not survive them.
REPO=${1:?repo}; C=${2:?campaign_dir}; RUN=${3:?run}; SEED=${4:?seed}; NEV=${5:?dummy_events}
P=$C/params/$RUN.data.json
D=$C/dummy/$RUN
W=${WORK:-${TMPDIR:-/tmp}/run_sim_$USER}/dummy_$RUN
get() { python3 -c 'import json,sys
d = json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): d = d[k]
print(d)' "$P" "$1"; }

[ -f "$P" ] || { echo "ERROR: no $P" >&2; exit 1; }
[ -d "$D" ] || mkdir "$D" || { echo "ERROR: cannot create $D" >&2; exit 1; }
mkdir -p "$W" && cd "$W" || exit 1
set -o pipefail
bash "$REPO/simulation/run/sim_digi_chunk.sh" "$REPO" "$NEV" "$(get particle)" "$(get E)" "$(get gun0.x)" "$(get gun0.y)" \
  "$(get gun0.sx)" "$(get gun0.sy)" "${SIGMA_E:-0.02}" "$SEED" "$(get set)" "$D/ecal_dummy_$RUN" \
  || { echo "ERROR: dummy simulation failed for $RUN"; exit 1; }

source "$REPO/init_siwecalsoft.sh" --no-venv --quiet || { echo "ERROR: init_siwecalsoft.sh failed" >&2; exit 1; }
command -v siwecal_beamspot >/dev/null || { echo "ERROR: siwecal_beamspot not on PATH (./build.sh)" >&2; exit 1; }
cp "$D/ecal_dummy_$RUN.root" "$W/" || { echo "ERROR: cannot read back the dummy tree"; exit 1; }
python3 "$REPO/reconstruction/jobs/run_pid_batch.py" --file "$W/ecal_dummy_$RUN.root" --outdir "$W" --format valtree \
  --hit-mip-cut 0.5 > "$W/pid.log" 2>&1 || { echo "ERROR: dummy PID failed for $RUN"; tail -20 "$W/pid.log"; exit 1; }
siwecal_beamspot measure "$W/ecal_dummy_$RUN.valtree.root" "$W/dummy_spot.json" || exit 1
siwecal_beamspot tune "$P" "$W/dummy_spot.json" "$W/params.json" || exit 1
cp "$W/ecal_dummy_$RUN.valtree.root" "$D/" && cp "$W/params.json" "$C/params/$RUN.json" \
  || { echo "ERROR: copy to $C failed"; exit 1; }
cat "$C/params/$RUN.json"
cd / && rm -rf "$W"
echo "DONE dummy $RUN"
