#!/bin/bash
# Aperture node (p2_<RUN> / p3_<RUN>) of a run with the rectangular far collimator: collimator_prep.py in the Key4hep
# environment. Runs on the shared filesystems (no file transfer): reads the campaign folder on EOS, writes the run's
# geometry under simulation/geometry/generated/.
#   run_collimator_prep.sh <repo> step2|step3 <args of collimator_prep.py>
# No set -e / set -u: key4hep's setup does not survive them.
REPO=${1:?repo}; shift
source "$REPO/init_siwecalsoft.sh" --no-venv --quiet || { echo "ERROR: init_siwecalsoft.sh failed" >&2; exit 1; }
exec python3 "$REPO/simulation/campaign/collimator_prep.py" "$@"
