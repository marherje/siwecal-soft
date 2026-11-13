#!/usr/bin/env bash
# One-time: the .venv with the event viewer's web stack (dash, plotly; seaborn without its deps) on top of key4hep.
#   source init_siwecalsoft.sh --no-venv && bash setup_venv.sh [--force]
# init_siwecalsoft.sh activates .venv from then on (--no-venv skips it).
set -eo pipefail
ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV="${ROOT}/.venv"
[ "${1:-}" = "--force" ] && rm -rf "${VENV}"
if [ -z "${KEY4HEP_STACK:-}" ]; then
    echo "ERROR: load key4hep first: source init_siwecalsoft.sh --no-venv" >&2; exit 1
fi
if [ ! -f "${VENV}/bin/activate" ]; then
    # --system-site-packages: numpy, uproot, ROOT, podio come from key4hep, the venv only adds the web stack
    python3 -m venv --system-site-packages "${VENV}"
fi
"${VENV}/bin/pip" install --quiet -r "${ROOT}/requirements.txt"
"${VENV}/bin/pip" install --quiet --no-deps -r "${ROOT}/requirements-nodeps.txt"
echo "[setup_venv] ${VENV} ready ($("${VENV}/bin/python3" --version)); source init_siwecalsoft.sh activates it"
