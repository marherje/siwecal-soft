#!/bin/bash
# Reconstruction of data runs that are ALREADY decoded, in one HTCondor DAG: per run, event building + PID (the RECO node
# of generate_reco_dag.py, same defaults as Reconstruction/) and then the valtree (pid_to_valtree.py).
#
#   bash data_conversion/jobs/condor/reco_decoded_runs.sh <runs list> [--submit]
#   <runs list>: first column = run name, '#' comments (e.g. simulation/campaign/runs_angle.txt, runs_pion.txt)
#
# The CONVERT nodes are DONE from the start: most eudaq runs are decoded in one chunk_0000.root while the generator lists
# every raw .bin file, so CONVERT would write chunk_0001... into the shared decoded data. Runs with an
# ecal_<RUN>.valtree.root in DATA_RECO are left alone (finished), so the same command can be used for a longer list.
# A run with only part of its files stops the script. A failed DAG is resumed with its rescue file
# (condor_submit_dag <dag>), not with this script.
#   DATA_RECO   output area, <RUN>/ecal_<RUN>.{root,edm4hep.root,valtree.root} (default Reconstruction)
# Without --submit it writes the DAG (and the empty run folders in DATA_RECO).
# No set -e / set -u: key4hep's setup does not survive them.
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
LIST=${1:-}
[ -f "$LIST" ] || { echo "usage: reco_decoded_runs.sh <runs list> [--submit]" >&2; exit 1; }
LIST="$(cd "$(dirname "$LIST")" && pwd)/$(basename "$LIST")"
case "$#:${2:-}" in 1:|2:--submit) ;; *) echo "ERROR: only --submit is accepted" >&2; exit 1 ;; esac
SUBMIT=${2:-}
source "$R/init_siwecalsoft.sh" --no-venv --quiet || { echo "ERROR: init_siwecalsoft.sh failed" >&2; exit 1; }
RECO=${DATA_RECO:-$(python3 -c 'from siwecal_common import paths; print(paths.reconstruction_dir())')} || exit 1
CONVERTED=$(python3 -m siwecal_common converted_dir) || exit 1
cd "$R" || exit 1

runs=""; n=0
for run in $(awk '!/^#/ && NF {print $1}' "$LIST"); do
  f=$RECO/$run/ecal_$run
  if [ -s "$f.valtree.root" ]; then echo "$run: done"; continue; fi
  for x in "$f.root" "$f.edm4hep.root"; do
    [ ! -e "$x" ] || { echo "ERROR: $x exists without its valtree: look at it first" >&2; exit 1; }
  done
  ls "$CONVERTED/$run/chunks/"chunk_*.root >/dev/null 2>&1 || { echo "ERROR: $run is not decoded" >&2; exit 1; }
  runs="$runs,$run"; n=$((n + 1))
done
[ "$n" -gt 0 ] || { echo "nothing to do"; exit 0; }

D=$R/work/condor_reco_$(basename "$LIST" .txt)_$(date +%Y%m%d_%H%M%S)   # a new folder per call
python3 data_conversion/jobs/condor/generate_reco_dag.py --no-validation --keep-job-logs --reco-dir "$RECO" \
  --runs "${runs#,}" --out-dir "$D" || exit 1
DAG=$D/reco.dag
sed -i 's/^JOB convert_.*/& DONE/' "$DAG"
if [ "$(grep -c '^JOB convert_' "$DAG")" != "$n" ] || [ "$(grep -c '^JOB convert_.* DONE$' "$DAG")" != "$n" ]; then
  echo "ERROR: CONVERT nodes not marked DONE, do NOT submit $DAG" >&2; exit 1
fi

cat > "$D/valtree.sh" <<EOF
#!/bin/bash
set -eo pipefail
source "$R/init_siwecalsoft.sh" --no-venv --quiet
python3 "$R/reconstruction/jobs/pid_to_valtree.py" "\$1"
[ -s "\${1%.edm4hep.root}.valtree.root" ]
EOF
chmod +x "$D/valtree.sh"
cat > "$D/valtree.sub" <<EOF
universe                = vanilla
executable              = $D/valtree.sh
arguments               = "\$(pid_out)"
log                     = $D/logs/valtree_\$(run).log
output                  = $D/logs/valtree_\$(run).out
error                   = $D/logs/valtree_\$(run).err
request_cpus            = 1
request_memory          = 6000
request_disk            = 8000M
should_transfer_files   = NO
getenv                  = False
+JobFlavour             = "longlunch"
queue
EOF
mkdir -p "$D/logs"
for run in ${runs//,/ }; do
  echo "JOB valtree_$run $D/valtree.sub"
  echo "VARS valtree_$run run=\"$run\" pid_out=\"$RECO/$run/ecal_$run.edm4hep.root\""
  echo "RETRY valtree_$run 2"
  echo "PARENT reco_$run CHILD valtree_$run"
done >> "$DAG"
echo "$n run(s), CONVERT nodes DONE; DAG: $DAG"
[ "$SUBMIT" != --submit ] || condor_submit_dag "$DAG"
