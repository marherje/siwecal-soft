#!/usr/bin/env python
"""
Batch driver for the Gaudi PID stage: resolve inputs exactly like
``siwecal_validation`` (--run / --file / --all / --point / --cfg) and run
``reconstruction/pid/options/run_pid.py`` once per ``ecal_<run>.root``.

The whole stage, event selection included, is ONE Gaudi job: this driver only
turns its options into the job's environment. ``EcalEventSelection`` applies the
cuts, the IOSvc writer and ``EcalValTreeWriter`` keep only the events it accepts,
and the job's options are the full record of the selection. Outputs:

* ``ecal_<label>.edm4hep.root`` -- the selected events, EDM4hep (``--format edm4hep|both``).
* ``ecal_<label>.valtree.root`` -- the same events as a flat valcache-schema TTree
  (``--format valtree|both``).

Run modes (``--validation``):

* default (physics): a hit-level MIP cut ``>= 0.5`` is baked in per cell and the
  ``mip05_/mip1_`` variant blocks are not computed.
* ``--validation`` (visualizer): no hit cut, and the MIP-variant blocks are
  computed in the Cluster (current behavior, for the online event viewer).

Cuts: every ``CutSet`` variable is a ``--<var>-min/--<var>-max`` flag, applied to
all runs; in ``--all``/``--point`` a per-energy ``cuts:`` block in the YAML
overrides them. Bounds are inclusive and a NaN value fails any bound. All cuts
default to off; events without hits or with non-positive total energy are always
dropped (``--keep-empty`` keeps them, so the outputs stay row-aligned with the
input ecal tree).

``--tracks-file`` merges a second EDM4hep file's ``ACTSTracks``/``EMShowers``/
``SiPadMeasurements``/``SiPadShowerFlags`` into the ``edm4hep`` output (same
events, same order: the job reads it as its IOSvc input). It exists for the
simulation case -- ``simulation/campaign/run_pid_sim.sh`` passes its own
``digitized.edm4hep.root`` explicitly -- and is entirely optional for real
test-beam data, which never has one to pass.

``--dry-run`` prints each job's environment and command without running it.

Run after ``source init_siwecalsoft.sh`` (key4hep plus this repo's install).
Example::

    python reconstruction/jobs/run_pid_batch.py --all --format both
    python reconstruction/jobs/run_pid_batch.py --run TB2026CERN_run_000007 --validation
"""
import argparse
import os
import shlex
import subprocess
import sys

import yaml

from siwecal_common import paths
from siwecal_validation.config import BASE_PATH, DEFAULT_CONFIG
from siwecal_validation.cli import cutset_from_args
from siwecal_validation.selection import CutSet, _CUT_SPEC

_STEERING = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pid", "options", "run_pid.py")


def _label(events_path):
    stem = os.path.splitext(os.path.basename(events_path))[0]
    return stem[len("ecal_"):] if stem.startswith("ecal_") else stem


def _resolve(events_path, base_path):
    if os.path.isabs(events_path):
        return events_path
    candidate = os.path.join(base_path, events_path)
    return candidate if os.path.exists(candidate) else paths.resolve_input(events_path)


def _jobs(args):
    """Yield (label, ecal_path, entry) triples from the CLI selection.

    ``entry`` is the YAML mapping for the sample (with an optional per-energy
    ``cuts:`` block and ``hit_mip_cut``), or ``{}`` for --run/--file.
    """
    if args.all or args.point is not None:
        with open(args.cfg) as handle:
            cfg = yaml.safe_load(handle) or {}
        data_map = cfg.get("event_data", {})
        if args.point is not None:
            data_map = {k: v for k, v in data_map.items() if k.startswith(f"P{args.point}_")}
        if not data_map:
            raise SystemExit(f"ERROR: no matching 'event_data' entries in {args.cfg}")
        base_path = cfg.get("main_path", BASE_PATH)
        for entry in data_map.values():
            path = _resolve(entry["path"], base_path)
            yield _label(path), path, entry
    elif args.file:
        yield (args.run or _label(args.file)), args.file, {}
    else:
        run = args.run or "TB2026CERN_run_000007"
        yield run, paths.resolve_input(os.path.join(run, f"ecal_{run}.root")), {}


def job_env(ecal_path, cut, *, tree="ecal", hit_cut=0.5, mip_thresholds=(),
            pid_out="", valtree_out="", tracks_file=None, keep_empty=False):
    """The environment of one ``run_pid.py`` job (on top of the caller's).

    ``pid_out``/``valtree_out`` empty = that output is not written. The selection
    (``PID_SELECT=1``) is always on: ``cut`` is a :class:`CutSet`.
    """
    return {
        "ECAL_FILE": ecal_path, "ECAL_TREE": tree,
        "ECAL_HIT_MIP_CUT": str(hit_cut),
        "ECAL_MIP_THRESHOLDS": ",".join(str(t) for t in mip_thresholds),
        "ECAL_PID_OUT": pid_out, "ECAL_VALTREE_OUT": valtree_out,
        "PID_SELECT": "1", "PID_REQUIRE_HITS": "0" if keep_empty else "1",
        "PID_CUTS": ",".join(cut.gaudi_cuts()), "PID_IS_SHOWER": str(cut.gaudi_is_shower),
        "PID_MERGE_FILE": tracks_file or "",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Batch Gaudi PID stage (ecal -> EDM4hep / valtree).")
    p.add_argument("--run", default=None, help="Single run name")
    p.add_argument("--file", default=None, help="Explicit ecal_<run>.root path")
    p.add_argument("--cfg", default=DEFAULT_CONFIG, help="data_reference YAML")
    bulk = p.add_mutually_exclusive_group()
    bulk.add_argument("--all", action="store_true", help="Every 'event_data' entry of the YAML")
    bulk.add_argument("--point", type=int, choices=range(1, 6), help="Only beam point P<N>_*")
    p.add_argument("--outdir", default=None,
                   help="Output directory. Default: settings.yml 'pid_dir', else "
                        "next to each input ecal file.")
    p.add_argument("--tracks-file", default=None, dest="tracks_file",
                   help="EDM4hep file (e.g. the simulation's digitized.edm4hep.root) "
                        "whose ACTSTracks/EMShowers/SiPadMeasurements/SiPadShowerFlags "
                        "are merged into the output at matching frame index. Explicit "
                        "only -- no sibling-file auto-discovery. Valid only with "
                        "--run/--file (a single input); rejected with --all/--point.")
    p.add_argument("--tree", default="ecal", help="Input TTree name")
    p.add_argument("--format", choices=("edm4hep", "valtree", "both"), default="edm4hep",
                   help="Output format(s) to write (default: edm4hep).")
    p.add_argument("--validation", action="store_true",
                   help="Visualizer mode: compute the mip05_/mip1_ variant blocks "
                        "and disable the hit-level MIP cut (current behavior). "
                        "Without it the hit cut defaults to >= 0.5 MIP and the "
                        "variant blocks are omitted.")
    p.add_argument("--hit-mip-cut", type=float, default=None, dest="hit_mip_cut",
                   help="Drop hits below this MIP energy (override; default: 0.5 "
                        "in physics mode, off with --validation).")
    p.add_argument("--keep-empty", action="store_true", dest="keep_empty",
                   help="Keep the events without hits or with non-positive energy "
                        "(EcalEventSelection RequireHits=False), so the outputs stay "
                        "row-aligned with the input ecal tree.")
    p.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Print each job's environment and command, run nothing.")
    # Event-selection cuts: one --<var>-min/--<var>-max per CutSet variable,
    # generated from the spec so the CLI never drifts from selection.py. All
    # default off; EcalEventSelection always drops the events without hits or
    # energy unless --keep-empty.
    cuts = p.add_argument_group(
        "selection cuts",
        "min/max bounds applied to all samples (per-energy YAML cuts override)")
    for field_min, field_max, _name, _attr in _CUT_SPEC:
        cuts.add_argument(f"--{field_min.replace('_', '-')}", type=float, default=None)
        cuts.add_argument(f"--{field_max.replace('_', '-')}", type=float, default=None)
    shower = cuts.add_mutually_exclusive_group()
    shower.add_argument("--is-shower", dest="is_shower", action="store_const",
                        const=True, default=None, help="keep only shower events")
    shower.add_argument("--no-shower", dest="is_shower", action="store_const",
                        const=False, help="keep only non-shower events")
    args = p.parse_args(argv)
    if args.tracks_file and (args.all or args.point is not None):
        raise SystemExit("--tracks-file only applies to a single run (--run/--file); "
                         "it cannot be combined with --all/--point.")

    general_cut = cutset_from_args(args)
    mip_thresholds = [0.5, 1.0] if args.validation else []
    default_hit_cut = -1.0 if args.validation else 0.5

    out_base = args.outdir or paths.pid_dir()   # None -> next to each input
    if out_base and not args.dry_run:
        os.makedirs(out_base, exist_ok=True)
    want_pid = args.format in ("edm4hep", "both")
    want_valtree = args.format in ("valtree", "both")
    failures = 0
    for label, ecal_path, entry in _jobs(args):
        if not os.path.exists(ecal_path) and not args.dry_run:
            print(f"SKIP {label}: not found ({ecal_path})")
            failures += 1
            continue
        out_dir = out_base or os.path.dirname(ecal_path)
        effective_cut = general_cut.merge(CutSet.from_mapping(entry.get("cuts")))
        hit_cut = (args.hit_mip_cut if args.hit_mip_cut is not None
                   else float(entry.get("hit_mip_cut", default_hit_cut)))
        pid_out = os.path.join(out_dir, f"ecal_{label}.edm4hep.root")
        # The EDM4hep goes to a hidden temporary and is renamed only when the job
        # succeeds (EcalValTreeWriter does the same for the valtree).
        temp = os.path.join(out_dir, f".{label}.pid.tmp.root")
        valtree_out = os.path.join(out_dir, f"ecal_{label}.valtree.root")
        env = job_env(ecal_path, effective_cut, tree=args.tree, hit_cut=hit_cut,
                      mip_thresholds=mip_thresholds,
                      pid_out=temp if want_pid else "",
                      valtree_out=valtree_out if want_valtree else "",
                      tracks_file=args.tracks_file if want_pid else None,
                      keep_empty=args.keep_empty)
        command = ["k4run", _STEERING]

        print(f"\n=== {label}: {ecal_path} (hit_mip_cut={hit_cut}, "
              f"mip_blocks={mip_thresholds or 'none'}, format={args.format}, "
              f"cuts={env['PID_CUTS'] or 'none'}, is_shower={env['PID_IS_SHOWER']}) ===")
        if args.dry_run:
            print(" ".join(f"{k}={shlex.quote(v)}" for k, v in env.items()) + " " + " ".join(command))
            continue
        result = subprocess.run(command, env={**os.environ, **env})
        if result.returncode != 0:
            print(f"ERROR: k4run failed for {label}")
            failures += 1
            if os.path.exists(temp):
                os.remove(temp)
            continue
        if want_pid:
            os.replace(temp, pid_out)
            if args.tracks_file:
                print(f"[Output] merged ACTSTracks from {args.tracks_file}")
            print(f"[Output] {pid_out}")
        if want_valtree:
            print(f"[Output] {valtree_out}")
    print(f"\n[Done] {failures} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
