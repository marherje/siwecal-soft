#!/usr/bin/env python3
"""Measure the chip baseline-sag maps (common/mappings/occupancy_sag_<set>.txt) with OccupancySagCalibrator:
one Fill per electron run (its decoded chunks), then one Table per threshold set. Replaces
analysis/cm_sag_collect.py + analysis/sag_table.py (same runs, chunks, selection and binning).

    python3 data_conversion/jobs/calibration/run_occupancy_sag.py <outdir> [--sets th210,th220,th230]
        [--chunks 10-17] [--max-acq N] [--fill-only] [--table-only]

Writes <outdir>/<run>.sagfill.txt and <outdir>/occupancy_sag_<set>.txt; copying the tables into common/mappings is
a deliberate step of its own. Every run's Fill reads a few GB from EOS: run it in batch (one job per run, e.g. with
condor), not on a login node; --max-acq gives a quick check.
"""
import argparse
import os
import subprocess
import sys

from siwecal_common import paths

# electron runs of each threshold set the official maps were measured on ('e' = eudaq run)
SETS = {"th210": ["e291", "e287", "e286"], "th220": ["67", "72"], "th230": ["20", "13", "12"]}
STEERING = paths.options_file("data_conversion", "run_occupancy_sag.py")


def run_name(r):
    return f"TB2026CERN_eudaq_run_{int(r[1:]):06d}" if r.startswith("e") else f"TB2026CERN_run_{int(r):06d}"


def k4run(env, log):
    with open(log, "w") as fh:
        rc = subprocess.run(["k4run", STEERING], env=dict(os.environ, **env), stdout=fh, stderr=subprocess.STDOUT).returncode
    if rc:
        sys.exit(f"k4run failed (exit {rc}), see {log}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--sets", default=",".join(SETS))
    ap.add_argument("--chunks", default="10-17", help="chunk range of every run (inclusive)")
    ap.add_argument("--max-acq", type=int, default=0)
    ap.add_argument("--fill-only", action="store_true")
    ap.add_argument("--table-only", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    c0, c1 = (int(x) for x in a.chunks.split("-"))
    for th in a.sets.split(","):
        fills = []
        for r in SETS[th]:
            fill = os.path.join(a.outdir, f"{r}.sagfill.txt")
            fills.append(fill)
            if a.table_only:
                continue
            chunks = [os.path.join(paths.converted_dir(), run_name(r), "chunks", f"chunk_{i:04d}.root")
                      for i in range(c0, c1 + 1)]
            chunks = [c for c in chunks if os.path.exists(c)]
            k4run({"SAG_MODE": "Fill", "SAG_INPUT_FILES": ",".join(chunks), "SAG_OUTPUT": fill,
                   "SAG_MAX_ACQ": str(a.max_acq)}, fill + ".log")
            print(f"[{th}] {r}: {len(chunks)} chunks -> {fill}")
        if a.fill_only:
            continue
        table = os.path.join(a.outdir, f"occupancy_sag_{th}.txt")
        k4run({"SAG_MODE": "Table", "SAG_FILL_FILES": ",".join(fills), "SAG_OUTPUT": table,
               "SAG_LABEL": f"{th}, from electron runs {', '.join(SETS[th])}"}, table + ".log")
        print(f"[{th}] -> {table}")


if __name__ == "__main__":
    main()
