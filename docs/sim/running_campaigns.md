# Running a simulation campaign (from your own account)

Setup shared by the ready-to-launch campaigns:
- [final_v11 without the occupancy sag](rerun_without_occupancy_sag.md) (`make_rerun_sim_dag.py`)
- [angular scan](angle_scan_simulation.md) (`launch_angle_scan.sh`, once the angle runs' data valtrees exist)

## 1. Checkout and build (once)

On lxplus (EL9), in your AFS area. The jobs read the scripts and `install/` of this checkout, so keep it for the
whole campaign: do not rebuild, pull or change branch in it while a DAG runs.

    git clone git@github.com:marherje/siwecal-soft.git && cd siwecal-soft
    git checkout far-collimator          # the branch with these launchers
    source init_siwecalsoft.sh           # Key4hep release pinned in .key4hep-release
    ./build.sh                           # Gaudi plugins, DD4hep detector, siwecal_beamspot -> install/
    python3 -m pytest -q tests/control/test_rerun_sim_dag.py tests/control/test_angle_scan.py

No `settings.yml` is needed: the defaults read the project area `/eos/experiment/drdcalo/siw-ecal/TB2026-06`.

## 2. Where the output goes

By default `Simulation/Processed/<campaign>/` in the project area: you need write access there (ask for it, or
check with `mkdir` in `Simulation/Processed/`). Otherwise give `--out` a folder of yours, e.g.
`--out /eos/user/<u>/<user>/siwecal/<campaign>` (the chunks are copied there with xrdcp, `eosuser` is recognised).
Either way the inputs (data valtrees, calibration, final_v11) are only read.

## 3. AFS quota

The DAG folder `work/condor_<campaign>/` gets one `.out`/`.err` per job (5221 chunks for final_v11) and DAGMan's
logs (~15 MB). final_v11's DAGMan died when the AFS quota filled up: check `fs lq` first (keep > 500 MB free) or put
the DAG elsewhere with `--dag-dir` (rerun) / in a checkout with room.

## 4. Launch

Always twice: first without `--submit` (writes the DAG only, prints one line per run; check the number of runs and
chunks), then the same command with `--submit`, from an lxplus login node (only the DAG is written there; the
simulation runs on HTCondor). Start with a small test (`--only <RUN>` and `--max-chunks` / `--max-events`, see each
page) and look at its output before the full campaign.

## 5. Follow and recover

    condor_q -batch                                       # progress of the DAG
    tail work/condor_<campaign>*/<campaign>.dag.dagman.out
    grep -l ERROR work/condor_<campaign>*/logs/*.out      # failed nodes and why

After a failure (a node out of retries, DAGMan killed), run the same command again: finished chunks and runs are
marked DONE and only what is missing is resubmitted. Each DAG folder keeps `launched_from.txt` and
`uncommitted.diff` (the code the jobs read).
