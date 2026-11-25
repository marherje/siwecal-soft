# Angular-scan simulation

Run-by-run simulation and reconstruction of the angular scan, as final_v11 but with the ECAL turned about the
vertical axis. Not run yet: it needs the data valtrees of the angle runs (the beam spot of each run is measured on
them, as in final_v11), which do not exist yet (`data_conversion/jobs/angular_scan/` builds the events; the valtree
comes after it).

- Runs: `simulation/campaign/runs_angle.txt`, the 20 positron runs of the physics scan (5, 10, 30 deg; 7.5, 10, 20,
  34, 52, 74 GeV; th210) and 4 muon runs at 45 deg (below). Left out: the 45 deg, 99 GeV positron runs (TDC and
  delay tests) and the runs without physics content.
- Geometry: `simulation/campaign/angle_geometry.py <campaign> <angle>` writes `generated/<campaign>/` copies of
  `SiPadDetector_beamline.xml` with the envelope rotation `y = <angle>*deg` and of `SND_compact_beamline.xml`
  including it. The box turns about its own centre (`Ecal_z_position`); in the test beam the pivot may have been
  elsewhere, which only moves the spot, and the tune follows the data spot anyway.
- Frames: the line and the gun stay along z; only the ECAL turns. DD4hep hits are in the world frame, the pad maps and
  the data in the ECAL's: `job3_digitize.py` reads the turn from the compact of the run (`COMPACT_FILE`,
  `siwecal_common.compact_geometry.ecal_turn_deg`) and `DetectorFlipper` (`LocalFrameCompact`) brings x, y to the ECAL
  frame with the placement in that geometry; it fails if the sample was not simulated with it. At 0 deg the output is
  unchanged. The gun is tuned in the lab, where x is cos(turn) shorter than in the ECAL (`BeamSpot.h`, `turn_deg`), and
  the far collimator is centred there too.
- Checked (2026-11-25, 30 muons per angle, undigitised): straight-line fit 10.1 +- 0.7, 29.9 +- 0.3 and 44.6 +- 1.0 deg
  at 10, 30 and 45 deg. The energy-weighted axis of 20 GeV electron showers (10 events) is biased low, about 25 deg at
  30 deg: an effect of the estimator on tilted layers, to be studied with the MC truth. At 45 deg a muon through the
  centre crosses about 10 layers.
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

## Muons, for tracking

Tracking is studied with muons: at normal incidence a muon stays in the same pad on most slabs, so the track
chi2/ndf sits near zero by construction (`docs/data/acts_integration.md`); turned at 45 deg it changes pad from slab
to slab and the fit quality means something.

- **45 deg**: runs 253 (th210), 254 (th220), 255 and 256 (th230), 150 GeV, label `M45` in `runs_angle.txt`;
  thresholds from each run's `Run_Settings.txt`. The rest of that muon scan (259-260, 265, 266: thresholds 205, 200,
  195) has no calibration tables. Data: `data_conversion/jobs/angular_scan/` (runs.yml, per-run `thresholds`), then
  `reconstruction/jobs/pid_to_valtree.py` for the valtree. Simulation: `ANGLES=45 bash
  simulation/campaign/launch_angle_scan.sh`.
- **0 deg**: `simulation/campaign/muon_points.txt` (runs e151, 85, 4), whose data valtrees already exist:

      python3 simulation/campaign/make_sim_dag.py --campaign muon_v1 --points simulation/campaign/muon_points.txt \
          --particle mu- --nevents 200000 --seed-offset 60000000      # check the printout; then the same with --submit

  Not `make_run_sim_dag.py --runs runs_muon.txt`: its spot is the one of the shower-like events. In run 4, where p90 of
  nhit is 454, that is 14.5 x 10.6 mm; its track-like events (n_layers_hit >= 10, nhit <= 30) give 36 x 39 mm.

At 45 deg the run-by-run tuning has the same problem: do not launch the 45 deg runs until their gun comes from track-like
events. The muon runs of the data also hold showers (run 4 above all): select the tracks.

Tests: `pytest tests/control/test_angle_scan.py`.
