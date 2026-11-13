#!/usr/bin/env python
"""
Write the valtree (valcache-schema ``ecal`` TTree) of already-produced PID EDM4hep files, without re-running the
PID stage: every event of ``ecal_<label>.edm4hep.root`` -> ``ecal_<label>.valtree.root`` next to it (or in
--outdir). One Gaudi job per file (reconstruction/pid/options/edm4hep_to_valtree.py), with the same
EcalValTreeWriter that run_pid_batch.py --format valtree|both runs inside the PID job.

    python reconstruction/jobs/pid_to_valtree.py <file.edm4hep.root> [...] [--outdir DIR] [--force]
    python reconstruction/jobs/pid_to_valtree.py --campaign /eos/.../Reconstruction      # every run in it

The MIP-variant blocks (mip05_/mip1_) are written only if the file carries them (validation mode): the options
file reads them from the file's ECalPid_shapeParameterNames metadata. Run after ``source init_siwecalsoft.sh``.
"""
import argparse
import glob
import os
import subprocess
import sys

_STEERING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pid", "options",
                         "edm4hep_to_valtree.py")


def valtree_path(path, outdir=None):
    label = os.path.basename(path)[len("ecal_"):-len(".edm4hep.root")]
    return os.path.join(outdir or os.path.dirname(path), f"ecal_{label}.valtree.root")


def convert(path, outdir=None, force=False, dry_run=False):
    """Run the valtree job for one PID file. Returns True on success (or skip)."""
    out = valtree_path(path, outdir)
    if os.path.exists(out) and not force:
        print(f"[skip] {out} exists")
        return True
    env = {"PID_FILE": path, "ECAL_VALTREE_OUT": out}
    command = ["k4run", _STEERING]
    if dry_run:
        print(" ".join(f"{k}={v}" for k, v in env.items()) + " " + " ".join(command))
        return True
    result = subprocess.run(command, env={**os.environ, **env})
    if result.returncode != 0:
        print(f"ERROR: k4run failed for {path}")
        return False
    print(f"[valtree] {path} -> {out}")
    return True


def select_files(files, campaign=None):
    files = list(files)
    if campaign:
        files += sorted(glob.glob(os.path.join(campaign, "*", "ecal_*.edm4hep.root")))
    # _moliere_/_weighte_: cut-study copies of a run, not runs of their own.
    return [f for f in files if f.endswith(".edm4hep.root") and "_moliere_" not in f and "_weighte_" not in f]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="*")
    p.add_argument("--campaign", default=None, help="Convert <campaign>/<run>/ecal_<run>.edm4hep.root for every run")
    p.add_argument("--outdir", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true", dest="dry_run", help="Print the jobs, run nothing")
    a = p.parse_args(argv)
    failures = sum(not convert(f, a.outdir, a.force, a.dry_run) for f in select_files(a.files, a.campaign))
    print(f"[Done] {failures} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
