#!/bin/bash
# ---------------------------------------------------------------------------
# run_pid_sim.sh
#
# PID of a digitised simulation sample, from the working directory (default work/mu_beam):
# SiWEcalPID (reconstruction/jobs/run_pid_batch.py) on the ecal tree that job3_digitize.py wrote next to its
# digitized.edm4hep.root (ECAL_TREE_OUTPUT=ecal_sim.root: the real chain; with DIGI_MODE=both the simple chain goes
# to ecal_sim_simple.root), with digitized.edm4hep.root's tracks merged in, for the event viewer and the validation.
#
# Prerequisites: ./build.sh done, environment from init_siwecalsoft.sh, and job3 run with ECAL_TREE_OUTPUT.
#
# Usage
# -----
#   source init_siwecalsoft.sh
#   bash simulation/campaign/run_pid_sim.sh [--validation] [--format {edm4hep,valtree,both}]
#                                [--outdir DIR] [--input digitized.edm4hep.root] [--ecal-tree ecal_sim.root]
#
# Outputs (default: work/mu_beam/)
#   ecal_sim.root           ecal TTree (intermediate, kept for inspection)
#   ecal_sim.edm4hep.root   SiWEcalPID output with shower variables
#   ecal_sim.valtree.root   plain TTree variant (with --format valtree/both)
# ---------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# --------------------------------------------------------------------------- #
# Defaults (can be overridden via CLI flags below)
# --------------------------------------------------------------------------- #
INPUT_EDM4HEP="${PWD}/digitized.edm4hep.root"
ECAL_TREE="${PWD}/ecal_sim.root"
OUT_DIR="${PWD}"
FORMAT="edm4hep"
VALIDATION_FLAG=""

# --------------------------------------------------------------------------- #
# Parse arguments
# --------------------------------------------------------------------------- #
while [[ $# -gt 0 ]]; do
    case "$1" in
        --validation)       VALIDATION_FLAG="--validation"; shift ;;
        --format)           FORMAT="$2"; shift 2 ;;
        --format=*)         FORMAT="${1#*=}"; shift ;;
        --outdir)           OUT_DIR="$2"; shift 2 ;;
        --outdir=*)         OUT_DIR="${1#*=}"; shift ;;
        --input)            INPUT_EDM4HEP="$2"; shift 2 ;;
        --input=*)          INPUT_EDM4HEP="${1#*=}"; shift ;;
        --ecal-tree)        ECAL_TREE="$2"; shift 2 ;;
        --ecal-tree=*)      ECAL_TREE="${1#*=}"; shift ;;
        -h|--help)
            sed -n '/^# Usage/,/^# Outputs/p' "$0" | grep -v '^#---'
            exit 0 ;;
        *)
            echo "Unknown flag: $1  (use --help for usage)"; exit 1 ;;
    esac
done

# --------------------------------------------------------------------------- #
# Verify SiWEcalPID build
# --------------------------------------------------------------------------- #
# the PID plugins (SiWEcalPID) are part of this repo's build: init_siwecalsoft.sh puts install/ on the paths
if [[ -z "${SIWECAL_SOFT_ROOT:-}" ]]; then   # key4hep does not survive set -u
    set +u; source "${REPO_ROOT}/init_siwecalsoft.sh" --no-venv --quiet; set -u
fi

# --------------------------------------------------------------------------- #
# The ecal tree written by job3 (EcalTreeWriter)
# --------------------------------------------------------------------------- #
echo ""
if [[ ! -f "${ECAL_TREE}" ]]; then
    echo "ERROR: no ecal tree ${ECAL_TREE}: run job3_digitize.py with ECAL_TREE_OUTPUT=$(basename "${ECAL_TREE}")"
    exit 1
fi

# --------------------------------------------------------------------------- #
# SiWEcalPID → EDM4hep / valtree with shower variables
# --------------------------------------------------------------------------- #
echo ""
echo "=== SiWEcalPID (shower variables + event selection) ==="
python3 "${REPO_ROOT}/reconstruction/jobs/run_pid_batch.py" \
    --file        "${ECAL_TREE}" \
    --tracks-file "${INPUT_EDM4HEP}" \
    --outdir      "${OUT_DIR}" \
    --format      "${FORMAT}" \
    ${VALIDATION_FLAG}

echo ""
echo "=== Done ==="
echo "Output directory: ${OUT_DIR}"
ls -lh "${OUT_DIR}"/ecal_sim*.root 2>/dev/null || true
