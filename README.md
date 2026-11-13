# siwecal-soft

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24204938.svg)](https://doi.org/10.5281/zenodo.24204938)

Software of the SiW-ECAL TB2026 test beam: data conversion, simulation, the reconstruction both share, and the
analysis that compares them. One repository, one CMake build, one install, one environment script, on Key4hep.

It replaces two repositories, frozen at the tag `final-before-monorepo`: `siwecal-tb2026` (data) and
`siwecal_k4sim` (simulation). `tools/migration/MIGRATED.tsv` records where each of their files went.

## Layout

| folder | what | Gaudi library |
|---|---|---|
| `common/` | the **only** copy of the mappings (pad maps, slab z, tungsten, digitisation tables), shared headers (`include/siwecal/`), `siwecal_common` (paths, slab description, EDM4hep PID reader, plot style) | – |
| `data_conversion/` | raw and LCIO decoding, event building, pedestal/MIP and gain-anchor calibration producers, reco DAGs, `siwecal_eventbuilder` | `SiWEcalDataConversion` |
| `reconstruction/` | what data and simulation share: PID (shower variables, event selection, valtree writer: one Gaudi job), ACTS tracking, the PID/valtree drivers | `SiWEcalPID`, `SiWEcalTracking` |
| `simulation/` | DD4hep detector and geometries (H2-like upstream line), ddsim launchers, digitisation, campaign DAGs | `SiWEcalSimDigi`, `SiPadDetector_plugin` |
| `analysis/` | data/simulation studies and the final plots (`analysis` package), `siwecal_validation`, run-list configs | – |
| `diagnostics/` | detector diagnostics on data (pedestals, MIP, common mode, ...) | – |
| `event_viewer/`, `event_display/` | the interactive viewer (data and simulation) and the event displays | – |
| `tests/control/` | control tests of the repo itself (paths, components, steering, beamline, physics smoke test) | – |

## Getting started (lxplus / NAF, EL9)

```bash
git clone <url> siwecal-soft && cd siwecal-soft
./build.sh                       # key4hep at the pinned release, cmake, install/, ctest + pytest
source init_siwecalsoft.sh       # every new shell (and every batch job): key4hep + install/ + Python packages
cp settings.example.yml settings.yml   # only if your data or calibration live elsewhere
bash setup_venv.sh               # once, for the event viewer (dash/plotly)
```

`init_siwecalsoft.sh` loads Key4hep at the release in `.key4hep-release` (`KEY4HEP_RELEASE` overrides it) and exports
`SIWECAL_SOFT_ROOT`, `SIWECAL_MAPPINGS`, `SIWECAL_CALIB_DIR` and `SIWECAL_PREFIX`. HTCondor jobs source the same file,
so a batch job runs in the same environment as an interactive shell.

## Where things are found

- **Python and shell** use `siwecal_common.paths`, or `python3 -m siwecal_common <key>` from a shell script, for the
  mappings, `calib_dir()/MuonCalib` (the official tables, on EOS), Reconstruction and Simulation. No calibration
  table is kept in the repo.
- **C++ components** open data files through `siwecal::resolveDataPath` (`common/include/siwecal/DataPath.h`). A
  relative name is looked up in `$SIWECAL_MAPPINGS`, then `$SIWECAL_SOFT_ROOT`, then the working directory.
- **Steering** (`*/options/*.py`, `simulation/jobs/*.py`) takes its inputs from environment variables. Without them
  it stops with a message that names what is missing.

## The chains

```
data        raw / .slcio --(data_conversion: decode, EcalEventBuilder + MuonCalib)--> ecal tree
simulation  ddsim (H2-like line, beam at -65.5 m, 2 % spread) --(job3_digitize: RealDigitizer +
            TimeOffsetNs, AdcDigitizer + measured occupancy sag)--> ecal tree (same format)
both        ecal tree --(reconstruction: EcalToEDM4hep + EcalShowerVariables + EcalEventSelection)--> EDM4hep PID + valtree --> analysis/
```

| campaign | how to produce it |
|---|---|
| data | `data_conversion/jobs/condor/generate_reco_dag.py` |
| simulation, per data run (final_v10 on) | `simulation/campaign/make_run_sim_dag.py --campaign <name> [--submit]` (per run: dummy pass tunes the gun to the run's beam, then production with its statistics; see `simulation/run/README.md`) |
| simulation, beam points (up to final_v9, muons, background) | `simulation/campaign/make_sim_dag.py --campaign <name> [--submit]` (one DAG: chunks, then groups) |

## Tests

```bash
./build.sh                                   # ctest + pytest (control tests included)
SIWECAL_SLOW_TESTS=1 pytest tests/control    # + the end-to-end physics smoke test (a few minutes)
```

The control tests check that:
- no personal or retired-repo path, and no `sys.path` hack, is left in the code;
- the repo holds no data or outputs, and the mappings exist once;
- every Gaudi component is defined once and its Configurable loads;
- every steering file configures;
- every launcher starts the beam upstream of its line;
- the pad maps sit on the DD4hep grid;
- the data and simulation slab readers agree;
- 40 events of 20 GeV electrons go through ddsim, digitisation with and without the occupancy sag, PID and valtree.

## Citing

See `CITATION.cff`. License: `LICENSE` (Apache-2.0), notices in `NOTICE`.
