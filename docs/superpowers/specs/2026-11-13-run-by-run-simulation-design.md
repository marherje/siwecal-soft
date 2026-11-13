# Run-by-run simulation campaign (final_v10): design

Status: approved 2026-11-13 (approach C and naming option 1 chosen by the user).

## Intent

Simplify simulation production: one simulated sample per data run, with the beam centre and spread measured on
that run and the same statistics, instead of the hand-maintained group table `simulation/campaign/beam_points.txt`
(94 points over 103 runs, one beam sigma per energy). The first campaign produced this way is **final_v10**.

Why now: the v9 review (2026-11-12) found the simulated spot 25–40 % too wide at 7.5–10 GeV. The gun sigmas of
`beam_points.txt` were derived (`analysis/beam_spread.py`, quadrature against a reference simulated with the beam
born at −2.65 m), but since 2026-10-26 the beam is born at −65.5 m and crosses the modelled H2 line
(~0.19 X0, ~39 m from the detector on average), whose multiple scattering widens the spot roughly as 1/E. A
per-run tuning pass done **with the production geometry** removes that bias by construction.

## Goals

- For every electron run: measure the beam centre and width in data, tune the gun with one short simulation of that
  run (the dummy pass), then produce the run's sample with the tuned gun.
- One DAG per campaign, everything on HTCondor, rerunnable (finished nodes are DONE, as `make_sim_dag.py` does).
- Every number used is written down: per-run parameter files and a closure table at the end.
- Existing analysis code reads the new campaign unchanged via a generated points file (`FINAL_GROUPS=`).

## Non-goals

- No change to the physics models (geometry, physics list, digitisation, sigma_E = 2 %).
- No iteration to convergence: one tuning step, then a closure check that is reported, not acted on automatically.
- Muon and background campaigns (`muon_points.txt`, `bkg_points.txt`) stay as they are.
- Angle-scan runs and extremely short runs (`--min-events`, default 5000 data events: runs 69, 67, 70, 68) are left out (user request).

## Anti-goals

- Anything that runs heavy work on the login node or submits without the user's confirmation.
- Writing into an existing campaign directory or anywhere on EOS outside the new campaign folder.

## Approaches considered

| | How the gun is set | Trade-off |
|---|---|---|
| A | quadrature formula per run against the existing −2.65 m reference | simplest; inherits the v9 bias |
| B | one reference sample per energy with the H2 line, then the formula per run | cheap, fixes the bias on average; assumes the line's widening is the same for every run at one energy |
| **C (chosen by the user)** | **per run: dummy simulation with an initial guess, measure, correct, then production** | most direct; one extra short sim + one extra measurement node per run |

## Design

### Run list

`simulation/campaign/runs_v10.txt`, one line per run: `RUN set label E particle` with `RUN` the full data name
(e.g. `TB2026CERN_eudaq_run_000291 th210 S1 20 e-`).
Generated once by a small tool from `beam_points.txt` (its runs column, with the set / label / energy of their
point; 103 electron runs), then maintained by hand. The 6 other runs of `Reconstruction/` are not electrons runs
of the scans and are left out unless added.

### Code split (user decision, 2026-11-13)

Every computation on events runs in C++; Python and bash only configure and orchestrate.
- C++: `common/include/siwecal/BeamSpot.h` (selection, centre, width, tuning, closure) and the executable
  `siwecal_beamspot` (ROOT TTree reader on valtrees, JSON out). Not a Gaudi algorithm: the valtrees are flat
  TTrees, and a k4run start per run would cost ~20 s each; the header can be wrapped in a Gaudi algorithm later.
- Python: the DAG writer and the final summary tables. bash: the node scripts.

### Per-run measurement (`siwecal_beamspot measure <valtree> <out.json>`)

On a valtree (data, dummy or production):
- selection as `analysis/beam_spread.py` / `final_panels.py`: shower-like events, `nhit_chan > 0.5 × p90`
  (p90 over all events of the file); only finite `bar_x`, `bar_y`;
- centre = median `bar_x`, `bar_y`; width = robust sigma `IQR / 1.349`; `n` = shower-like events.

The data parameters are estimated from the final data valtrees in `Reconstruction/` when the DAG is written
(no measurement node): this fixes the number of production chunks up front.

### Tuning step (`siwecal_beamspot tune`)

Initial guess for the dummy: gun centre = data centre, gun sigma = data width (floor 1 mm). After the dummy:

    x_gun  = x_dummy_gun + (median_data − median_dummy)          (same for y)
    s_gun² = s_dummy_gun² + w_data² − w_dummy²                    (per axis; floor at 1 mm)

i.e. the `beam_spread.py` quadrature, but with the reference simulated for this run, with the H2 line.

### Statistics

Production events = `n` (shower-like) of the data run, rounded up to whole chunks of 2000 (minimum one chunk).
Dummy: 3000 events (one node, no chunking).

### DAG (per run), `simulation/campaign/make_run_sim_dag.py --campaign final_v10 [--submit]`

    DUMMY ─► CHUNK_000..N ─► GROUP          (per run)
    all GROUP nodes ─► SUMMARY

- DAG writing (login node, light): `siwecal_beamspot measure` on every data valtree → `params/<RUN>.data.json`
  (data measurement, initial gun, `n_events`, `n_chunks`). Runs without a valtree or with 0 shower-like events
  are skipped with a message.
- `DUMMY` (`run_sim_dummy.sh`): `sim_digi_chunk.sh` with the initial gun, PID `--format valtree` on the real tree,
  `siwecal_beamspot measure` + `tune` → `params/<RUN>.json` (adds the dummy measurement and the tuned gun).
- `CHUNK_k` (`run_sim_chunk.sh`): reads the tuned gun from `params/<RUN>.json` at run time, calls `sim_digi_chunk.sh`.
- `GROUP` (`run_sim_group.sh`): hadd + PID `--format both` (hit MIP cut 0.5) for digi and nodigi, written to the
  per-run layout below; `siwecal_beamspot measure` + `closure` on the digitised valtree → `closure/<RUN>.json`.
- `SUMMARY` (Python): `closure.tsv` (flags |Δcentre| > 1 mm or |Δwidth| > 5 %) and `beam_points_v10.txt`.
- Seeds: `SEED_OFFSET + line_index_in_run_list * 1000 + chunk` (dummy: chunk 999); eudaq and non-eudaq run
  numbers collide, so the run number itself is not used.
- Geometry/physics/digitiser exactly as `make_sim_dag.py` today (H2 compact, `BEAM_Z_MM=-65500`, QGSP_BERT_EMZ,
  `job3_digitize.py` defaults, reco with th210 table).

### Output on EOS: `Simulation/Processed/final_v10/`

Naming (chosen by the user): one folder per run named exactly like its data folder in `Reconstruction/`, files
named like the data files with `sim_` after the `ecal_` prefix, and `_nodigi` for the undigitised variant:

    final_v10/<RUN>/ecal_sim_<RUN>.root                      ecal tree, digitised (the one compared with data)
    final_v10/<RUN>/ecal_sim_<RUN>.edm4hep.root              PID
    final_v10/<RUN>/ecal_sim_<RUN>.valtree.root              valtree
    final_v10/<RUN>/ecal_sim_<RUN>_nodigi.{root,edm4hep.root,valtree.root}
    e.g. <RUN> = TB2026CERN_run_000022, TB2026CERN_eudaq_run_000291

`run_pid_batch.py` keeps these names as they are (input `ecal_sim_<RUN>.root` → label `sim_<RUN>`). Work areas
next to the run folders: `params/<RUN>{.data,}.json`, `dummy/<RUN>/`, `chunks/<RUN>/` (removed by the group node,
as today), `closure/<RUN>.json`, `closure.tsv`, and `beam_points_v10.txt` (generated, one line per run in the `beam_points.txt`
format with the tuned gun) so `FINAL_GROUPS=.../beam_points_v10.txt python analysis/final_panels.py` works.

## Constraints

- Login node: only DAG writing and dry runs. Every `condor_submit` is confirmed by the user.
- EOS: only the new `final_v10/` tree; plain `mkdir` per level.
- Key4hep via `init_siwecalsoft.sh`; no `set -u` in job scripts.

## Testing

- C++ tests (ctest): `BeamSpot.h` on synthetic data (Gaussian, shower-like cut, NaN, empty, tuning floor, closure
  flags) and `siwecal_beamspot` end to end on a small generated valtree.
- DAG writing: `--dry-run` test that writes the DAG for 2 runs into a tmp dir and checks node graph + params.
- Small real test (with confirmation): one run, dummy 500 + production 2 × 500, campaign `test_v10` under
  `Simulation/tests/run_by_run/`, then the user decides on final_v10.

## Left to the builder

File and function names beyond those above, closure thresholds, log/retry settings, exact wrapper interface.
