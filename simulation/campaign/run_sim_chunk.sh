#!/bin/bash
# One production chunk of one run (node c_<RUN>_<NNN> of simulation/campaign/make_run_sim_dag.py): the tuned gun is read
# from params/<RUN>.json at run time (the dummy node wrote it after the DAG was made), then sim_digi_chunk.sh.
#
#   run_sim_chunk.sh <repo> <campaign_dir> <RUN> <chunk> <seed> <chunk_events>
#   out: <campaign_dir>/chunks/<RUN>/ecal_sim_<RUN>_c<NNN>{,_simple}.root
# Environment (from the .sub): COMPACT_FILE, BEAM_Z_MM, PHYSICS_LIST, RECO_TABLE, SIGMA_E (default 0.02).
REPO=${1:?repo}; C=${2:?campaign_dir}; RUN=${3:?run}; K=${4:?chunk}; SEED=${5:?seed}; CH=${6:?chunk_events}
P=$C/params/$RUN.json
get() { python3 -c 'import json,sys
d = json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."): d = d[k]
print(d)' "$P" "$1"; }

[ -f "$P" ] || { echo "ERROR: no $P (dummy node not done?)" >&2; exit 1; }
NEV=$(( $(get n_events) - K * CH )); [ "$NEV" -gt "$CH" ] && NEV=$CH
[ "$NEV" -gt 0 ] || { echo "ERROR: chunk $K beyond n_events of $RUN" >&2; exit 1; }
[ -d "$C/chunks/$RUN" ] || mkdir "$C/chunks/$RUN"
exec bash "$REPO/simulation/run/sim_digi_chunk.sh" "$REPO" "$NEV" "$(get particle)" "$(get E)" "$(get gun.x)" "$(get gun.y)" \
  "$(get gun.sx)" "$(get gun.sy)" "${SIGMA_E:-0.02}" "$SEED" "$(get set)" "$(printf '%s/chunks/%s/ecal_sim_%s_c%03d' "$C" "$RUN" "$RUN" "$K")"
