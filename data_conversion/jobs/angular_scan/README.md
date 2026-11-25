# angular_scan pipeline — runs 179-239 (th210)

Event-builds + validates (EDM4hep/PID) the angular-scan run range, from
chunks **already decoded** into `rundata_converted_gaudi/<RUN>/chunks/`
(see `data_conversion/jobs/condor/generate_convert_eudaq_dag.py` and
`data_conversion/jobs/decode_lcio_runs.py` for how those chunks were produced). This
pipeline does **no CONVERT step** — it only reads chunks that must already
exist.

One parametrised steering pair for all runs: `steer_eventbuild.py` (event builder) and `validate.py`
(EDM4hep + PID), with the run in `ANGSCAN_RUN` and the run list and threshold in `runs.yml`
(siwecal-tb2026 kept 55 copies of each, which differed only in the run number). The 55 positron runs are
**th210**, calibrated with the official tables, `calib_dir()/MuonCalib/*/th210/`. The 4 muon runs at 45 deg
(150 GeV, a threshold scan) take the tables of their own threshold, from `thresholds` in `runs.yml`: 253 th210,
254 th220, 255 and 256 th230 (ThresholdDAC of their `Run_Settings.txt`). The other runs of that muon scan,
259-260 (205), 265 (200) and 266 (195), have no calibration tables and are left out; 272 has 1005 events.

## Runs

179-239 inclusive (61 run numbers), minus 6 excluded:

- **197, 217, 218, 219, 220**: no raw or converted data exists for these run
  numbers at all (no `rundata/TB2026CERN_..._run_0002NN` folder under either
  naming) -- a gap in the run numbering, not a filter.
- **225**: a `chunks/chunk_0000.root` exists but holds 0 entries -- this is
  one of the 5 runs `data_conversion/jobs/condor/classify_eudaq_routes.py` could not
  resolve during the eudaq conversion (`route: "failed"` in
  `data_conversion/jobs/condor/generated/convert_eudaq/route_map.json`: 0 entries via
  the raw decoder and no `Data/eudaq/ROC_run_000225_tp.slcio` to fall back
  to). Its input simply doesn't exist yet; re-run
  `classify_eudaq_routes.py --runs TB2026CERN_eudaq_run_000225` if the raw or
  LCIO source data ever turns up, then regenerate its steer/validate pair
  from another run's pair as a template.

That leaves **55** run pairs (`steer_*.py` / `validate_*.py`), all
`TB2026CERN_eudaq_run_0001NN`.

## Run one

```bash
source init_siwecalsoft.sh

k4run data_conversion/jobs/angular_scan/steer_TB2026CERN_eudaq_run_000179.py
k4run data_conversion/jobs/angular_scan/validate_TB2026CERN_eudaq_run_000179.py
```

Output goes to `rundata_converted_gaudi/<RUN>/events/` (next to that run's
`chunks/`, not the shared `Reconstruction/` area):
`ecal_<RUN>.root` (event builder) then `ecal_<RUN>.edm4hep.root` (PID/EDM4hep).

## Run all 56

```bash
source init_siwecalsoft.sh

bash data_conversion/jobs/angular_scan/run_all.sh
```

Sequential, local, idempotent (skips a run whose `ecal_<RUN>.edm4hep.root`
already exists unless `--force`); on lxplus run it inside an HTCondor job.

**Do not submit the CONVERT nodes of `data_conversion/jobs/condor/generate_reco_dag.py` for the positron runs.**
They are decoded in one `chunk_0000.root`, but the generator lists every raw `.bin` file and CONVERT would write
chunk_0001... into the shared decoded data. To use that DAG, mark the `JOB convert_*` lines `DONE` first (as
`simulation/campaign/launch_pions.sh reco` does).

## Adapt to a different run / threshold

Copy one `steer_*.py`/`validate_*.py` pair, change `_RUN` (and `_TH` if the
new run isn't th210 — check its calibration tables exist under
`calibration/MuonCalib_gaudi/{pedestals,mips,anchor}/th<N>/` first).
