# Run-by-run simulation (final_v10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One HTCondor DAG that, per electron data run, tunes the gun with a short dummy simulation and then produces
a simulated sample with the run's beam and statistics, named after the run.

**Architecture:** All event-level computation is C++: header `common/include/siwecal/BeamSpot.h` and executable
`siwecal_beamspot` (measure / tune / closure on valtrees, JSON in and out). Python writes the DAG (measuring the data
valtrees with `siwecal_beamspot` when it does) and the final summary tables; bash node scripts chain the existing
simulation (`sim_digi_chunk.sh`), PID (`run_pid_batch.py`) and `siwecal_beamspot`.

**Tech Stack:** C++20, ROOT (TTree), nlohmann_json 3.12 (key4hep), CTest; Python 3; bash; HTCondor DAGMan.

**Spec:** `docs/superpowers/specs/2026-11-13-run-by-run-simulation-design.md`

## Global Constraints

- Per run output `Simulation/Processed/<campaign>/<RUN>/ecal_sim_<RUN>.{root,edm4hep.root,valtree.root}` and `ecal_sim_<RUN>_nodigi.{...}`; `<RUN>` = data folder name (`TB2026CERN_run_000022`, `TB2026CERN_eudaq_run_000291`).
- Work areas: `params/<RUN>.data.json`, `params/<RUN>.json`, `dummy/<RUN>/`, `chunks/<RUN>/`, `closure/<RUN>.json`, `closure.tsv`, `beam_points_v10.txt`.
- Selection: shower-like `nhit_chan > 0.5 * p90(nhit_chan)` (p90 over all events, linear interpolation like `np.percentile`); finite `bar_x`, `bar_y` only; centre = median; width = (q75 − q25)/1.349.
- Tune: `x_gun = x_dummy_gun + (x_data - x_dummy)`; `s_gun^2 = s_dummy_gun^2 + w_data^2 - w_dummy^2`; floor 1 mm. Initial gun = data centre and width (floor 1 mm).
- Statistics: production events = data `n` rounded up to whole chunks of 2000, minimum 1 chunk; dummy 3000 events.
- Closure flag: |Δx| or |Δy| > 1 mm, or |w_sim/w_data − 1| > 0.05 on either axis.
- Physics unchanged: `COMPACT_FILE=SND_compact_beamline.xml BEAM_Z_MM=-65500 PHYSICS_LIST=QGSP_BERT_EMZ RECO_TABLE=th210`, sigma_E 0.02, PID hit MIP cut 0.5.
- Seeds: `seed_offset + line_index * 1000 + chunk`, dummy chunk 999.
- EOS: only the new campaign folder, plain `mkdir` per level; no `set -u` in scripts; nothing submitted without the user's confirmation; the user commits.

## Review Focus

1. Very few or 0 shower-like events: `measure` returns `n = 0` with NaN centre/width (JSON `null`), never crashes; the DAG writer skips such runs.
2. Dummy wider than data: `s_gun^2 < 0` → floor 1 mm, never NaN.
3. NaN/inf `bar_x`, `bar_y` (valtree scalars are NaN for some events): excluded.
4. Missing data valtree: DAG writer prints `SKIP <RUN>: no valtree` and goes on.
5. Rerun after partial failure: dummy DONE if `params/<RUN>.json` exists, chunk DONE if both chunk trees exist, group DONE if both run valtrees exist.

---

### Task 1: `BeamSpot.h`

**Files:** Create `common/include/siwecal/BeamSpot.h`, `common/tests/test_beam_spot.cpp`; Modify `common/CMakeLists.txt` (test `beam_spot`).

**Interfaces (namespace `siwecal::beamspot`):**
- `struct Spot { double x, y, wx, wy; long n; };`  `struct Gun { double x, y, sx, sy; };`
- `double percentile(std::vector<double> v, double q);` (q in [0,100], linear interpolation; empty → NaN)
- `Spot measure(const std::vector<int>& nhit, const std::vector<double>& barX, const std::vector<double>& barY);`
- `Gun initialGun(const Spot& data, double floorMm = 1.0);`
- `Gun tune(const Spot& data, const Spot& dummy, const Gun& dummyGun, double floorMm = 1.0);`
- `long productionEvents(long nShowerlike, long chunk = 2000);`
- `struct Closure { double dx, dy, rwx, rwy; bool flag; };  Closure closure(const Spot& data, const Spot& sim, double maxShiftMm = 1.0, double maxRelWidth = 0.05);`

- [ ] Step 1: tests (plain asserts, exit code): Gaussian 20000 events x~N(5,10), y~N(−3,4), nhit 100 → |x−5|<0.3, |wx−10|<0.3, n==20000; nhit = 500×1 + 500×100 → n==500; half NaN barX → finite result, n counts finite only; empty → n==0, isnan(x); tune data(x10,w12) dummy(x8,w13) gun(x10,s12) → x==12, sx==sqrt(119); floor: data w2, dummy w20, gun s3 → sx==1; productionEvents(1)=2000, (2000)=2000, (2001)=4000, (0)=2000; closure dx .5 & rw .02 → no flag, dx 1.5 → flag, rw −.06 → flag; percentile({1,2,3,4},50)==2.5.
- [ ] Step 2: build + `ctest -R beam_spot` → FAIL (missing header)
- [ ] Step 3: implement
- [ ] Step 4: `ctest -R beam_spot` → PASS

### Task 2: `siwecal_beamspot` executable

**Files:** Create `common/src/siwecal_beamspot.cpp`, `common/tests/test_beamspot_exe.sh`; Modify `common/CMakeLists.txt` (executable linked to ROOT::Tree, nlohmann_json; installed to `bin`; test `beamspot_exe`).

**Interfaces (CLI):**
- `siwecal_beamspot measure <valtree.root> <out.json> [--tree ecal]` → `{"x","y","wx","wy","n"}` (NaN → `null`)
- `siwecal_beamspot tune <params.data.json> <dummy_spot.json> <out_params.json>`: reads `data` and `gun0` from the first, writes the first file's content plus `"dummy": <spot>`, `"gun": {x,y,sx,sy}`
- `siwecal_beamspot closure <params.json> <sim_spot.json> <out.json>` → `{"data":…, "sim":…, "dx","dy","rwx","rwy","flag"}`
- exit code ≠ 0 with a message on unreadable input.

- [ ] Step 1: test script: writes a 3000-event valtree with ROOT (`root -l -b -q` macro, branches `nhit_chan/I bar_x/D bar_y/D`), runs `measure`, checks `n` and centre with `python3 -c json` ; runs `tune` and `closure` on hand-written JSON and checks values.
- [ ] Step 2: `ctest -R beamspot_exe` → FAIL
- [ ] Step 3: implement (TTree::SetBranchAddress loop; valtree `bar_x`, `bar_y` are `/D`, `nhit_chan` `/I`)
- [ ] Step 4: `ctest -R beamspot_exe` → PASS

### Task 3: Run list

**Files:** Create `simulation/campaign/make_run_list.py`, `simulation/campaign/runs_v10.txt`, `tests/control/test_run_list.py`.

**Interfaces:** `run_name(token) -> str` (`"e291"` → `TB2026CERN_eudaq_run_000291`, `"22"` → `TB2026CERN_run_000022`); `read_runs(path) -> list[dict]` keys `run, set, label, E, particle` (format `RUN set label E particle`, `#` comments).

- [ ] Step 1: tests `test_run_name`; `test_runs_v10_covers_beam_points` (103 runs, each with its point's set/label/E, particle `e-` unless given); `test_runs_exist_in_reconstruction` (`eos` fixture).
- [ ] Step 2: FAIL → Step 3: implement + generate → Step 4: PASS

### Task 4: Node scripts and summary

**Files:** Create `simulation/campaign/run_sim_dummy.sh`, `run_sim_chunk.sh`, `run_sim_group.sh`, `campaign_summary.py`, `tests/control/test_campaign_summary.py`.

**Interfaces:**
- `run_sim_dummy.sh <repo> <campaign_dir> <RUN> <seed> <dummy_events>`: gun0 from `params/<RUN>.data.json`; `sim_digi_chunk.sh` → `dummy/<RUN>/ecal_dummy_<RUN>{,_simple}.root`; PID `--format valtree --hit-mip-cut 0.5` on the real one; `siwecal_beamspot measure` + `tune` → `params/<RUN>.json`.
- `run_sim_chunk.sh <repo> <campaign_dir> <RUN> <chunk> <seed> <chunk_events>`: gun from `params/<RUN>.json`; events = min(chunk_events, n_events − chunk·chunk_events); remote `chunks/<RUN>/ecal_sim_<RUN>_c<NNN>`.
- `run_sim_group.sh <repo> <campaign_dir> <RUN> <nchunks>`: hadd per mode → PID `--format both --hit-mip-cut 0.5` → `<RUN>/ecal_sim_<RUN>{,_nodigi}.*`; measure + closure on the digitised valtree → `closure/<RUN>.json`; removes `chunks/<RUN>`.
- JSON values read in bash with `python3 -c 'import json,sys; …'` (orchestration only).
- `campaign_summary.py <campaign_dir> <runs_file>`: `closure.tsv` (RUN E, data x y wx wy n, gun x y sx sy, sim x y wx wy, dx dy rwx rwy flag; `missing` for runs without closure) and `beam_points_v10.txt` (`beam_points.txt` format: name=RUN, set, label, E, gun x y sx sy rounded 0.1 mm, runs=RUN, particle).

- [ ] Step 1: tests: summary on a tmp campaign (2 runs, one without closure) → 2 rows, one `missing`; `beam_points_v10.txt` parses with `make_sim_dag.read_points` and carries the tuned gun.
- [ ] Step 2: FAIL → Step 3: implement scripts + summary → Step 4: tests PASS, `bash -n` on the scripts, `test_repo_hygiene.py` PASS.

### Task 5: DAG writer

**Files:** Create `simulation/campaign/make_run_sim_dag.py`, `tests/control/test_run_sim_dag.py`.

**Interfaces:** `make_run_sim_dag.py --campaign NAME [--runs runs_v10.txt] [--only RUN,...] [--out DIR] [--dag-dir DIR] [--data-reco DIR] [--dummy-events 3000] [--chunk-events 2000] [--max-events N] [--seed-offset 20000000] [--submit]`. Measures each data valtree with `siwecal_beamspot measure` into `<dag-dir>/params/<RUN>.data.json` (with `gun0`, `n_events`, `n_chunks`, run metadata); copies `params/` to `<out>/params/` only with `--submit`. Nodes `d_<RUN>`, `c_<RUN>_<NNN>`, `g_<RUN>`, `summary`; flavours `tomorrow` for E ≥ 52 else `workday`.

- [ ] Step 1: tests (need `siwecal_beamspot` on PATH → `k4env` fixture): fake reco dir with run A (4500 shower-like events, generated with uproot) and run B (no valtree): graph d→3 c→g→summary for A, `SKIP` for B; data json `n_events 6000`, `n_chunks 3`; DONE detection for the dummy; `--max-events 1000 --chunk-events 500` → 2 chunks.
- [ ] Step 2: FAIL → Step 3: implement → Step 4: PASS, then `./build.sh -j 4` all green.

### Task 6: Docs and the small real test (needs the user)

- [ ] Docs: `README.md` campaign table, `simulation/run/README.md` "Run-by-run campaigns".
- [ ] Test DAG without submit: `--campaign test_v10 --out .../Simulation/tests/run_by_run/test_v10 --only TB2026CERN_eudaq_run_000291 --dummy-events 500 --max-events 1000 --chunk-events 500`; show it to the user; submit only after confirmation.
- [ ] After the test: `final_v10` DAG without submit for review; the user confirms the submit.
- [ ] Propose the commits; update checklist artifact, memory, handoff note.
