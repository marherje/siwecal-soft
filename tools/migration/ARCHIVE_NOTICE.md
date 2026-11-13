# Notice for the top of the README of the two frozen repositories

Paste this block above the first heading of `siwecal_k4sim/README.md` and of `siwecal-tb2026/README.md`, commit it on
top of the tag `final-before-monorepo`, then archive the repository on GitHub (Settings > Archive this repository).

---

> **This repository is frozen and archived.** Its code now lives in **siwecal-soft**, together with the
> <simulation | test-beam data> software, under one CMake build and one environment (`init_siwecalsoft.sh`).
> The last state of this repository is the tag `final-before-monorepo`. `tools/migration/MIGRATED.tsv` in
> siwecal-soft lists where each of its files went.
>
> | here | in siwecal-soft |
> | --- | --- |
> | `gaudi_source/` (k4SiWEcalReco), `gaudi_jobs/` | `data_conversion/`, `reconstruction/` (PID, tracking) |
> | `gaudi_source/`, `detector_plugin/`, `gaudi_jobs/pid2026_common/` (SND_reco) | `simulation/digitisation/`, `simulation/detector/`, `simulation/jobs/` |
> | `mappings/` | `common/mappings/` (the only copy) |
> | `calibration/MuonCalib_*`, `masking_info/` | not in the repo: `calib_dir()/MuonCalib` on EOS |
> | `setup.sh`, `init_key4hep.sh`, `init_siwecal_soft.sh` | `init_siwecalsoft.sh` |
