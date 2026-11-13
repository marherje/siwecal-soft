#!/usr/bin/env bash
# Environment of siwecal-soft. Source it, never execute it:   source init_siwecalsoft.sh [--no-venv] [--quiet]
#
#  - key4hep, at the release pinned in .key4hep-release (KEY4HEP_RELEASE overrides it for one shell); skipped when
#    that release is already loaded, refused when a different one is (key4hep cannot be loaded twice).
#  - the repo:  SIWECAL_SOFT_ROOT  repo root          SIWECAL_MAPPINGS  common/mappings (the only copy)
#               SIWECAL_PREFIX     install prefix     SIWECAL_CALIB_DIR calibration root (settings.yml calib_dir, EOS)
#  - the build: plugin libraries on LD_LIBRARY_PATH, Configurables + the repo's Python packages on PYTHONPATH,
#               the DD4hep detector plugin on the DD4hep plugin path.
#  - .venv (dash/plotly for the event viewer), when it exists and --no-venv is not given.
# Condor jobs source this same file on the worker (AFS), so the batch environment is the interactive one.
# No `set -u` anywhere in this chain: key4hep's own setup does not survive it.

_SWS_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]:-$0}" )" && pwd )"
_SWS_VENV=1; _SWS_QUIET=0
for _a in "$@"; do
    case "$_a" in
        --no-venv) _SWS_VENV=0 ;;
        --quiet)   _SWS_QUIET=1 ;;
        *) echo "init_siwecalsoft.sh: unknown option $_a" >&2; return 1 ;;
    esac
done

# ---- key4hep ---------------------------------------------------------------------------------------------------
source "${_SWS_ROOT}/key4hep_release.sh"
if [ -z "${KEY4HEP_RELEASE:-}" ]; then
    KEY4HEP_RELEASE="$(k4_release "${_SWS_ROOT}")" || return 1
fi
if k4_stack_is "${KEY4HEP_RELEASE}"; then
    :
elif [ -n "${KEY4HEP_STACK:-}" ]; then
    echo "ERROR: this shell already has another key4hep loaded: ${KEY4HEP_STACK}" >&2
    echo "       siwecal-soft wants ${KEY4HEP_RELEASE}. Start a new shell." >&2
    return 1
else
    source /cvmfs/sw.hsf.org/key4hep/setup.sh -r "$(k4_setup_release "${KEY4HEP_RELEASE}")" >/dev/null || return 1
fi

# ---- the repo ----------------------------------------------------------------------------------------------------
export SIWECAL_SOFT_ROOT="${_SWS_ROOT}"
export SIWECAL_MAPPINGS="${_SWS_ROOT}/common/mappings"
export SIWECAL_PREFIX="${SIWECAL_PREFIX:-${_SWS_ROOT}/install}"

_sws_prepend() {   # _sws_prepend VAR dir: put dir first in VAR, once
    local var="$1" dir="$2" cur
    cur="${!var}"
    case ":${cur}:" in *":${dir}:"*) cur="$(printf '%s' ":${cur}:" | sed "s#:${dir}:#:#g; s#^:##; s#:\$##")" ;; esac
    export "${var}=${dir}${cur:+:${cur}}"
}
for _d in "${_SWS_ROOT}" "${_SWS_ROOT}/analysis/python" "${_SWS_ROOT}/data_conversion/python" \
          "${_SWS_ROOT}/common/python" "${SIWECAL_PREFIX}/python"; do
    _sws_prepend PYTHONPATH "$_d"
done
for _d in "${SIWECAL_PREFIX}/lib" "${SIWECAL_PREFIX}/lib64"; do
    [ -d "$_d" ] && _sws_prepend LD_LIBRARY_PATH "$_d"
done
# the repo's executables (siwecal_beamspot)
[ -d "${SIWECAL_PREFIX}/bin" ] && _sws_prepend PATH "${SIWECAL_PREFIX}/bin"
# DD4hep finds the SiPadDetector plugin (lib*.components) through LD_LIBRARY_PATH; ROOT needs the rootmap path too.
[ -d "${SIWECAL_PREFIX}/lib" ] && _sws_prepend ROOT_LIBRARY_PATH "${SIWECAL_PREFIX}/lib"

# calibration root: settings.yml (or SIWECAL_SETTINGS) calib_dir, through the same code the Python side uses
if [ -z "${SIWECAL_CALIB_DIR:-}" ]; then
    SIWECAL_CALIB_DIR="$(python3 -m siwecal_common calib_dir 2>/dev/null)" && export SIWECAL_CALIB_DIR \
        || unset SIWECAL_CALIB_DIR
fi

# ---- build state -------------------------------------------------------------------------------------------------
_SWS_MSG=""
if [ ! -d "${SIWECAL_PREFIX}" ]; then
    _SWS_MSG="no install/ yet: run ./build.sh"
elif [ -d "${_SWS_ROOT}/build" ] && [ -n "$(find "${_SWS_ROOT}/build" -maxdepth 3 -name '*.so' -newer "${SIWECAL_PREFIX}" -print -quit 2>/dev/null)" ]; then
    _SWS_MSG="build/ is newer than install/: run cmake --install build"
fi

# ---- viewer venv -------------------------------------------------------------------------------------------------
if [ "$_SWS_VENV" = 1 ] && [ -f "${_SWS_ROOT}/.venv/bin/activate" ] && [ "${VIRTUAL_ENV:-}" != "${_SWS_ROOT}/.venv" ]; then
    source "${_SWS_ROOT}/.venv/bin/activate"
fi

if [ "$_SWS_QUIET" = 0 ]; then
    echo "[siwecal-soft] key4hep ${KEY4HEP_RELEASE}${VIRTUAL_ENV:+ + $(basename "${VIRTUAL_ENV}")}, root ${SIWECAL_SOFT_ROOT}"
    [ -n "${SIWECAL_CALIB_DIR:-}" ] && echo "[siwecal-soft] calibration: ${SIWECAL_CALIB_DIR}"
    [ -n "$_SWS_MSG" ] && echo "[siwecal-soft] WARNING: ${_SWS_MSG}" >&2
fi
unset _SWS_ROOT _SWS_VENV _SWS_QUIET _SWS_MSG _a _d
unset -f _sws_prepend
