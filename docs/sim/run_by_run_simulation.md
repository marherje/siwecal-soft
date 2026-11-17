# Run-by-run simulation (final_v10 on)

Design of the simulation campaigns made per data run (2026-11-13). How to run them: `simulation/run/README.md`.

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
- Angle-scan runs and extremely short runs (`--min-events`, default 5000 data events: runs 69, 67, 70, 68) are left out.

## Anti-goals

- Anything that runs heavy work on the login node or submits a campaign without review of its DAG.
- Writing into an existing campaign directory or anywhere on EOS outside the new campaign folder.

## Approaches considered

| | How the gun is set | Trade-off |
|---|---|---|
| A | quadrature formula per run against the existing −2.65 m reference | simplest; inherits the v9 bias |
| B | one reference sample per energy with the H2 line, then the formula per run | cheap, fixes the bias on average; assumes the line's widening is the same for every run at one energy |
| **C (adopted)** | **per run: dummy simulation with an initial guess, measure, correct, then production** | most direct; one extra short sim + one extra measurement node per run |

## Design

### Run list

`simulation/campaign/runs_v10.txt`, one line per run: `RUN set label E particle` with `RUN` the full data name
(e.g. `TB2026CERN_eudaq_run_000291 th210 S1 20 e-`).
Generated once by a small tool from `beam_points.txt` (its runs column, with the set / label / energy of their
point; 103 electron runs), then maintained by hand. The 6 other runs of `Reconstruction/` are not electrons runs
of the scans and are left out unless added.

### Code split

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
- Optional far collimator, per beam energy: `--far-collimator 7.5=23` puts 1 m of iron jaws (square hole, half-side
  23 mm, centred on the run's data spot) at -26 m (`--far-collimator-z`) in the runs at 7.5 GeV only; the runs of
  any other energy keep the free line. Each collimated run gets its own compact,
  `simulation/geometry/generated/<campaign>/<RUN>.xml` (git-ignored), passed to its dummy and chunks as
  `COMPACT_FILE`; `params/<RUN>.data.json` records `compact` and `far_collimator`. The jaws may not overlap any
  element of the line (free slots: -26, -33.5, -42.5 m). Why per energy: the 7.5 GeV spot of the data has truncated
  tails that the free line does not give, the 20 and 74 GeV spots do not, and in H2 the collimators were set run by
  run (collimator tests, 2026-11). The tune assumes widths add in quadrature, which a cut breaks: check the closure of
  the collimated runs (two dummy passes may be needed). The jaws stop part of the beam (shower-like fraction 0.40-0.44
  at 7.5 GeV with a = 25 mm, 0.92 without), so a collimated run simulates `n / --far-collimator-transmission`
  events (default 0.4) to match the statistics of the data, and its dummy has `--far-collimator-dummy-events`
  (default 6000) instead of 3000; both are recorded in `params/<RUN>.data.json`.
- Rectangular far collimator per run and per axis, `--rect-collimator 7.5,10` (used by final_v11). A fixed square hole
  leaves the spot too wide in y and too narrow in x (in H2 the horizontal and vertical collimators are independent),
  so for the runs of those energies the apertures are found at run time, per axis:
  `d1` free-line dummy (`collimator/pass1/`) → `p2` (`collimator_prep.py step2`): jaws on an axis only if the
  free-line tune hits the floor (gun sigma < 0.35 × data width: the line alone is too wide) or the free line's tails
  are wider than the data's by > 0.10, first half-aperture = data width / 0.88, gun sigma = data width; otherwise no
  jaws and the tuned gun → `d2` dummy with the jaws (`collimator/pass2/`) → `p3` (`step3`): aperture + (w_data −
  w_d2) / 0.45 (step ≤ 6 mm), writes `params/<RUN>.json` and the run's geometry
  `simulation/geometry/generated/<campaign>/<RUN>.xml` (a run left open on both axes gets the base line) → chunks.
  Decisions and tails per axis: `collimator/<RUN>{.step2,}.json`. Tails ((p95 − p5) / IQR of the barycentre) are
  computed in Python in the node (uproot), not in `BeamSpot.h`: the C++ could not be rebuilt while final_v11 ran;
  move them there later. Collimator tests (2026-11-16, 8 runs 7.5–74 GeV, `work/beam_collimator/make_rect.py`):
  width within ±5 % of the data everywhere; jaws needed only at 7.5 and 10 GeV, mostly in y; shower shapes as with the
  free line, except about −0.1σ in hits and energy for the run collimated on both axes (run 57).

### Output on EOS: `Simulation/Processed/final_v10/`

Naming: one folder per run named exactly like its data folder in `Reconstruction/`, files
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

- Login node: only DAG writing and dry runs; the campaign runs on HTCondor.
- EOS: only the campaign's own tree; plain `mkdir` per level.
- Key4hep via `init_siwecalsoft.sh`; no `set -u` in job scripts.
- While a campaign runs, do not rebuild or switch branches in the repo: the jobs read its scripts and `install/`.

## Tests

- ctest: `beam_spot` (`BeamSpot.h` on synthetic data: Gaussian, shower-like cut, NaN, empty, tuning floor, closure
  flags) and `beamspot_exe` (`siwecal_beamspot` end to end, checked against the numpy definition of
  `analysis/beam_spread.py`).
- pytest `tests/control/`: `test_run_list.py` (run list vs `beam_points.txt`, no angle-scan runs),
  `test_run_sim_dag.py` (DAG graph, data parameters, skipped runs, DONE detection), `test_campaign_summary.py`.

## final_v10

Launched 2026-11-13: 99 runs (67, 68, 69, 70 skipped as too short), 7.88 M shower-like events → 3990 chunks of 2000.

## final_v11

Launched 2026-11-17 in two DAGs writing to the same `Simulation/Processed/final_v11/`:
- `work/condor_final_v11/`: the 87 runs at 20 GeV and above (67, 68, 69, 70 skipped as too short), free line, as
  final_v10 (the collimator tests left every axis open there); 3167 chunks. Launched from fd76286 plus uncommitted
  changes that do not affect these runs (`launched_from.txt`, `uncommitted.diff` in that folder).
- `work/condor_final_v11_low/`: the 12 runs at 7.5 and 10 GeV with `--rect-collimator 7.5,10` and
  `--seed-offset 30000000` (no seed shared with the first DAG).
The summary of the first DAG covers its 87 runs; run `campaign_summary.py` on the whole run list once both are done.
