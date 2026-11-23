# Angular-scan simulation

Run-by-run simulation and reconstruction of the angular scan, as final_v11 but with the ECAL turned about the
vertical axis. Not run yet: it needs the data valtrees of the angle runs (the beam spot of each run is measured on
them, as in final_v11), which do not exist yet (`data_conversion/jobs/angular_scan/` builds the events; the valtree
comes after it).

- Runs: `simulation/campaign/runs_angle.txt`, the 20 runs of the physics scan (5, 10, 30 deg; 7.5, 10, 20, 34, 52,
  74 GeV; th210). Left out: the 45 deg, 99 GeV runs (TDC and delay tests) and the runs without physics content.
- Geometry: `simulation/campaign/angle_geometry.py <campaign> <angle>` writes `generated/<campaign>/` copies of
  `SiPadDetector_beamline.xml` with the envelope rotation `y = <angle>*deg` and of `SND_compact_beamline.xml`
  including it. The box turns about its own centre (`Ecal_z_position`); in the test beam the pivot may have been
  elsewhere, which only moves the spot, and the tune follows the data spot anyway.
- Launcher: `simulation/campaign/launch_angle_scan.sh` (usage, options and environment in its header): per angle, the
  geometry and one DAG of `make_run_sim_dag.py` (`--rect-collimator 7.5,10`, `--seed-offset 40000000 + angle *
  100000`, `--no-summary`), all into `Simulation/Processed/<CAMPAIGN>/` (default `angle_v1`); then
  `campaign_summary.py` on `runs_angle.txt`. It stops if a data valtree is missing (`DATA_RECO`, `ALLOW_MISSING=1`).

Setup first (checkout, build, EOS write access, AFS quota): [running_campaigns.md](running_campaigns.md). Options
after the launcher's own go to `make_run_sim_dag.py`, e.g. `--out <your EOS folder>`.

Before the full campaign, check the turned geometry on one run (Geant4 overlaps at 30 deg, direction of the turn
against the data: `ANGLE_SIGN=-1` turns the other way):

    CAMPAIGN=test_angle ANGLES=30 bash simulation/campaign/launch_angle_scan.sh --only TB2026CERN_eudaq_run_000212 \
        --dummy-events 500 --max-events 1000 --chunk-events 500 --submit

Tests: `pytest tests/control/test_angle_scan.py`.
