#!/usr/bin/env bash
# The event viewer on simulation output (a PID file of simulation/campaign/run_pid_sim.sh or of a campaign's pid/).
#   source init_siwecalsoft.sh            (with .venv: bash setup_venv.sh once)
#   bash event_viewer/launch_sim.sh [--port 8050] [--file PATH] [--data-dir DIR] [--debug]
# then http://localhost:8050 (through an SSH tunnel from lxplus).
set -eo pipefail
ROOT="${SIWECAL_SOFT_ROOT:?source init_siwecalsoft.sh first}"
PORT=8050; ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --port) PORT="$2"; shift ;;
        --file|--data-dir) ARGS+=("$1" "$2"); shift ;;
        --debug) ARGS+=("--debug") ;;
        -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
        *) echo "unknown flag $1" >&2; exit 1 ;;
    esac
    shift
done
if [[ ! " ${ARGS[*]} " =~ " --file " ]]; then
    for c in "${ROOT}/work/mu_beam/ecal_sim.edm4hep.root" "${ROOT}/work/mu_beam/ecal_sim.valtree.root"; do
        [ -f "$c" ] && { ARGS+=(--file "$c"); echo "[launch_sim] $c"; break; }
    done
fi
export SIWECAL_SETTINGS="${ROOT}/event_viewer/sim_settings.yml"
cd "${ROOT}"
exec python3 -m event_viewer --port "${PORT}" "${ARGS[@]}"
