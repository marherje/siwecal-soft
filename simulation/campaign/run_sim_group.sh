#!/bin/bash
# One run after all its chunks (node g_<RUN> of simulation/campaign/make_run_sim_dag.py): hadd the chunk trees, run the
# PID job (EDM4hep + valtree, hit MIP cut 0.5) for the digitised and the undigitised sample, measure the simulated spot
# and write the closure against the data (siwecal_beamspot). Output named like the data, with sim_ after ecal_:
#
#   run_sim_group.sh <repo> <campaign_dir> <RUN> <nchunks>
#   in : <campaign_dir>/chunks/<RUN>/ecal_sim_<RUN>_cNNN{,_simple}.root
#   out: <campaign_dir>/<RUN>/ecal_sim_<RUN>.{root,edm4hep.root,valtree.root}       digitised
#        <campaign_dir>/<RUN>/ecal_sim_<RUN>_nodigi.{root,edm4hep.root,valtree.root}  undigitised
#        <campaign_dir>/closure/<RUN>.json; the chunk trees are removed at the end
REPO=${1:?repo}; C=${2:?campaign_dir}; RUN=${3:?run}; NCH=${4:?nchunks}
W=${WORK:-${TMPDIR:-/tmp}/run_sim_$USER}/group_$RUN
O=$C/$RUN

source "$REPO/init_siwecalsoft.sh" --no-venv --quiet || { echo "ERROR: init_siwecalsoft.sh failed" >&2; exit 1; }
command -v hadd >/dev/null && command -v siwecal_beamspot >/dev/null || { echo "ERROR: hadd/siwecal_beamspot missing" >&2; exit 1; }
set -o pipefail
[ -d "$O" ] || mkdir "$O" || { echo "ERROR: cannot create $O" >&2; exit 1; }
mkdir -p "$W"

for mode in real simple; do
  if [ $mode = real ]; then sfx=""; name=ecal_sim_$RUN; else sfx=_simple; name=ecal_sim_${RUN}_nodigi; fi
  shopt -s nullglob; trees=("$C/chunks/$RUN"/ecal_sim_${RUN}_c[0-9][0-9][0-9]${sfx}.root); shopt -u nullglob
  [ ${#trees[@]} -eq "$NCH" ] || { echo "ERROR: $RUN $mode: ${#trees[@]}/$NCH chunk trees" >&2; exit 1; }
  hadd -f "$W/$name.root" "${trees[@]}" > "$W/hadd_$mode.log" 2>&1 || { echo "ERROR: hadd $RUN $mode"; tail -5 "$W/hadd_$mode.log"; exit 1; }
  python3 "$REPO/reconstruction/jobs/run_pid_batch.py" --file "$W/$name.root" --outdir "$W" --format both --hit-mip-cut 0.5 \
    > "$W/pid_$mode.log" 2>&1 || { echo "ERROR: PID $RUN $mode"; tail -20 "$W/pid_$mode.log"; exit 1; }
  for ext in root edm4hep.root valtree.root; do
    f=$W/$name.$ext
    cp "$f" "$O/" && [ "$(stat -c %s "$f")" = "$(stat -c %s "$O/$name.$ext")" ] || { echo "ERROR: copy $f"; exit 1; }
  done
done

siwecal_beamspot measure "$W/ecal_sim_$RUN.valtree.root" "$W/sim_spot.json" || exit 1
siwecal_beamspot closure "$C/params/$RUN.json" "$W/sim_spot.json" "$C/closure/$RUN.json" || exit 1
cat "$C/closure/$RUN.json"
rm -rf "$W" "$C/chunks/$RUN"
echo "DONE $RUN"
