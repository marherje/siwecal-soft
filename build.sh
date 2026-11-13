#!/usr/bin/env bash
# Build, install and test siwecal-soft in one go:   ./build.sh [-j N] [--clean] [--no-test]
# Runs in its own shell (sources init_siwecalsoft.sh itself). Login nodes are shared: keep -j modest (default 8).
JOBS=8; CLEAN=0; TEST=1
while [ $# -gt 0 ]; do
    case "$1" in
        -j) JOBS="$2"; shift ;;
        --clean) CLEAN=1 ;;
        --no-test) TEST=0 ;;
        *) echo "usage: ./build.sh [-j N] [--clean] [--no-test]" >&2; exit 2 ;;
    esac
    shift
done
ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "${ROOT}/init_siwecalsoft.sh" --no-venv --quiet || exit 1
[ "$CLEAN" = 1 ] && rm -rf "${ROOT}/build" "${ROOT}/install"
cmake -S "${ROOT}" -B "${ROOT}/build" -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_INSTALL_PREFIX="${ROOT}/install" \
      -DCMAKE_EXPORT_COMPILE_COMMANDS=ON || exit 1
cmake --build "${ROOT}/build" -j "${JOBS}" || exit 1
cmake --install "${ROOT}/build" >/dev/null || exit 1
echo "[build] installed to ${ROOT}/install"
if [ "$TEST" = 1 ]; then
    source "${ROOT}/init_siwecalsoft.sh" --no-venv --quiet
    ctest --test-dir "${ROOT}/build" --output-on-failure || exit 1
    (cd "${ROOT}" && python3 -m pytest -q) || exit 1
fi
