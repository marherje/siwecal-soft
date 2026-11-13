# siwecal_eventbuilder

The Python side of the Gaudi event builder (`EcalEventBuilder`, `data_conversion/src/`): what the drivers need to
configure `data_conversion/options/run_event_builder.py` for a run.

| module | what |
|---|---|
| `calib_files` | the MuonCalib tables of a run (`resolve_gaudi_calib_files`, default th210 pedestals and MIPs), its LG->HG anchor line (`read_gain_anchor`), the per-slab pad maps (`PAD_MAP_FILES_DEFAULT`) |
| `geometry` | the slab description in the data-side shape (`load_slab_technology`, a view of `siwecal_common.slab_description`), slab z and W thicknesses |
| `run_settings` | the threshold DAC of a run, from its `Run_Settings.txt` |

The event building itself is Gaudi's only. siwecal-tb2026 also had a pure-Python event builder (`cli.py`,
`pipeline.py`, `hit_collector.py`, `bcid_clustering.py`, ...), the predecessor of `EcalEventBuilder`, which no chain
used any more; it is retired (its code is in siwecal-tb2026 at the tag `final-before-monorepo`).
