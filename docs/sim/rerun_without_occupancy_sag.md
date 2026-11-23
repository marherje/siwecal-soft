# final_v11 without the occupancy sag

How to rebuild the run-by-run campaign final_v11 with the chip baseline sag (the occupancy-dependent pedestal shift,
`AdcDigitizer` `OccupancySagTable`) switched off in the digitisation, everything else as final_v11.

## What is kept and what changes

`simulation/campaign/make_rerun_sim_dag.py` re-runs a finished campaign without tuning it again:

| | from |
|---|---|
| runs (99; 67–70 skipped as too short) | `Processed/final_v11/params/<RUN>.json` |
| tuned gun, events per run, chunks | same files |
| far collimator of the 7.5 and 10 GeV runs | written again from `far_collimator` in those files, identical to final_v11's geometries (checked) |
| Geant4 seed of every chunk | `simulation/campaign/seeds_final_v11.txt` (extracted from the final_v11 DAGs) |
| line, physics list, beam z, energy spread, reco table | defaults of `make_run_sim_dag.py`, as final_v11 |
| **digitiser** | **`OCCUPANCY_SAG_TABLE='' OCCUPANCY_SLOPE=0`** in the chunks' environment (`job3_digitize.py`: sag OFF) |

So with the same Key4hep release the Geant4 showers are the same events as final_v11 and the difference between the
two campaigns is the digitisation. Not bit for bit beyond Geant4: the sag also decides the trigger survival of the
hits, so the digitiser's random stream is not consumed the same way.

## Running it

Setup first (checkout, build, EOS write access, AFS quota): [running_campaigns.md](running_campaigns.md). Then, on
an lxplus login node (it only writes the DAG):

    source init_siwecalsoft.sh
    python3 simulation/campaign/make_rerun_sim_dag.py --source final_v11 --campaign final_v11_nosag --no-occupancy-sag
    # check the printout (99 runs, 5221 chunks); then the same command with --submit

- Output: `Simulation/Processed/final_v11_nosag/`, same layout and names as final_v11
  (`<RUN>/ecal_sim_<RUN>{,_nodigi}.{root,edm4hep.root,valtree.root}`, `closure.tsv`, `beam_points_v10.txt`).
  `--out <dir>` writes elsewhere (needs write access there). The `_nodigi` samples do not use the digitiser, so
  they are the same as final_v11's.
- DAG and logs: `work/condor_final_v11_nosag/`. Each chunk's `.out` prints `[job3] occupancy baseline sag OFF`.
- After a failure, run the same command again: finished chunks and runs are marked DONE.
- Provenance: `launched_from.txt` and `uncommitted.diff` in the DAG folder, `rerun.json` in the output and a `rerun`
  block in every `params/<RUN>.json` (source, digitiser environment, commit).
- While it runs do not rebuild or change branch in that checkout: the jobs read its scripts and `install/`.
- Other digitiser variations: `--digi-env NAME=VALUE` (repeatable), any switch of `simulation/jobs/job3_digitize.py`.
- Test on a few chunks first: `--campaign test_nosag --only TB2026CERN_run_000022 --max-chunks 2`.

## Results

`analysis/final_v11_results_job.sh <out>` with `SIM=<...>/Processed/final_v11_nosag` (on HTCondor) gives the same
panels, MIP → GeV, scans and profiles for this campaign.

## Tests

`pytest tests/control/test_rerun_sim_dag.py` (DAG graph, seeds, digitiser environment, geometries, refused inputs).
