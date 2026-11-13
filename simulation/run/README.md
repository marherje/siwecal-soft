# Simulation run scripts

## Output location

Simulation output (`.edm4hep.root` files produced by `ddsim`) is written directly to EOS:

```
/eos/experiment/drdcalo/siw-ecal/TB2026-06/Simulation/
```

The local `data/` subdirectory is no longer used and should not be created.

## Scripts

| Script | Description |
|--------|-------------|
| `generic_condor_beam.sh` | HTCondor job for beam-test simulation (GPS-driven) |
| `generic_condor_PG.sh`   | HTCondor job for particle-gun simulation |
| `launch_beam.sh`         | Wrapper to submit beam jobs |
| `launch_PG.sh`           | Wrapper to submit PG jobs |
| `clean.sh`               | Remove generated steer/log files |

## Run-by-run campaigns (final_v10 on)

One simulated sample per data run, with that run's beam and statistics
(design: `docs/superpowers/specs/2026-11-13-run-by-run-simulation-design.md`).

```bash
source init_siwecalsoft.sh
python3 simulation/campaign/make_run_sim_dag.py --campaign final_v10            # writes work/condor_final_v10/, review it
python3 simulation/campaign/make_run_sim_dag.py --campaign final_v10 --submit   # ... and condor_submit_dag
```

- Runs: `simulation/campaign/runs_v10.txt` (`RUN set label E particle`, `RUN` = data folder in `Reconstruction/`;
  generated from `beam_points.txt` by `make_run_list.py`, then edited by hand). Normal incidence only; runs with fewer
  than `--min-events` (default 5000) events in the data valtree are skipped.
- Beam spot (C++, `siwecal_beamspot` / `common/include/siwecal/BeamSpot.h`): shower-like events
  (`nhit_chan > 0.5 * p90`), centre = median `bar_x`/`bar_y`, width = IQR / 1.349.
- Per run: `d_<RUN>` simulates 3000 events with the data centre and width as gun, measures them and tunes the gun,
  `x_gun += x_data - x_dummy`, `s_gun^2 = s_gun^2 + w_data^2 - w_dummy^2` (floor 1 mm) -> `params/<RUN>.json`;
  `c_<RUN>_NNN` produce the data's shower-like statistics, rounded up to chunks of 2000; `g_<RUN>` merges, runs the
  PID job and writes the closure (simulated vs data spot) -> `closure/<RUN>.json`.
- Output `Simulation/Processed/<campaign>/<RUN>/ecal_sim_<RUN>{,_nodigi}.{root,edm4hep.root,valtree.root}`, plus
  `closure.tsv` (flagged: centre off by > 1 mm or width by > 5 %) and `beam_points_v10.txt` for the analysis
  (`FINAL_GROUPS=.../beam_points_v10.txt`).
