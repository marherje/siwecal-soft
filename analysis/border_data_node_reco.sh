#!/bin/bash
# Same as border_data_node.sh, but keeping the events without hits (run_pid_batch.py --keep-empty, i.e.
# EcalEventSelection RequireHits=False), like the Reconstruction campaign's own recipe (generate_reco_dag.py reco.sh),
# so the EDM4hep and the valtree stay row-aligned with ecal_<run>.root. Hit MIP cut 0.5 and mip05_/mip1_ blocks, as
# reco.sh. Used for the runs that have empty events (107, 111, 116, 134).
#
#   bash analysis/border_data_node_reco.sh <run> <reco_base> <out_base>
RUN=${1:?run}; RECO=${2:?reco_base}; O=${3:?out_base}
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
W=${WORK:-${TMPDIR:-/tmp}/border_data_reco_$USER}/$RUN
IN=$RECO/$RUN/ecal_$RUN.root

[ -f "$IN" ] || { echo "missing input $IN" >&2; exit 1; }
mkdir -p "$W"
set -o pipefail
(cd "$R" && \
  python3 reconstruction/jobs/run_pid_batch.py --file "$IN" --outdir "$W" --format both --validation --hit-mip-cut 0.5 \
    --keep-empty > "$W/pid.log" 2>&1) \
  || { echo "pid FAILED $RUN"; tail -40 "$W/pid.log"; exit 1; }
[ -d "$O/$RUN" ] || mkdir "$O/$RUN"
for kind in edm4hep valtree; do
  f=$W/ecal_$RUN.$kind.root
  [ -s "$f" ] || { echo "no $kind for $RUN"; tail -5 "$W/pid.log"; exit 1; }
  cp "$f" "$O/$RUN/" || { echo "copy FAILED $RUN $kind"; exit 1; }
  [ "$(stat -c %s "$f")" = "$(stat -c %s "$O/$RUN/$(basename "$f")")" ] || { echo "size mismatch $RUN $kind"; exit 1; }
done
cp "$W/pid.log" "$O/$RUN/"
rm -rf "$W"
echo "DONE $RUN"
