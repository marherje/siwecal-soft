# ACTS tracking: one implementation for data and simulation

The two former repositories each had ACTSGeoSvc, ACTSProtoTracker, ShowerTagger and SiPadMeasConverter, with the
same component names and diverging code. In siwecal-soft each exists once, in `reconstruction/tracking/`
(library `SiWEcalTracking`):

| component | difference between the copies | resolution |
|---|---|---|
| `ISNDGeoSvc` | a comment | one header |
| `ACTSProtoTracker` | the include path | one source |
| `ACTSGeoSvc` | where the 15 planes come from: the DD4hep DetElement tree of the compact (sim, full slice stack as surface material) or `slab_z_positions.yml` (data, W only, nominal thickness, HalfSizeX/Y envelope) | `GeometrySource = auto/dd4hep/slabz`; `planesFromDD4hep()` / `planesFromSlabZ()` feed the same scaffolding (identical in both copies) |
| `ShowerTagger` | input type (`SimCalorimeterHit` / `CalorimeterHit`), cellID field (`layer` / `slab`), default input and BitField | class template over the hit collection (`siwecal::HitTraits`), components `ShowerTagger` (data) and `SimShowerTagger` (simulation); `LayerField` property |
| `SiPadMeasConverter` | as ShowerTagger, plus the hit time (`getTime()` / first MC contribution) | template, `SiPadMeasConverter` and `SimSiPadMeasConverter`; time from `HitTraits::time` |

Steering: `reconstruction/tracking/options/run_tracking.py` (data, `GeometrySource="slabz"`) and
`simulation/jobs/job4_tracking.py` (simulation, `Sim*` components, `GeometrySource="dd4hep"`).
The uniqueness of every component name is enforced at configure time (`cmake/CheckUniqueComponents.cmake`) and by
`tests/control/test_components.py`.

Regression (2026-11-13), unified library against the frozen builds, same inputs, every EDM4hep branch compared:
- data: `run_tracking.py` on 200 events of eudaq run 166 (Reconstruction PID file), siwecal-tb2026's
  `libk4SiWEcalRecoPlugins` vs `SiWEcalTracking`: 137 branches, all identical (NaN == NaN);
- simulation: `job4_tracking.py` on 40 events of 20 GeV electrons through the H2-like line (`SiPadHits`),
  siwecal_k4sim's `libSND_reco` vs `SimShowerTagger`/`SimSiPadMeasConverter`/`ACTSGeoSvc` (dd4hep): 144 branches,
  all identical.
The old simulation job only ran with siwecal_k4sim's own plugins on the path: with `init_siwecal_soft.sh`, which also
loaded siwecal-tb2026's, the tb2026 `ACTSGeoSvc` Configurable (no `CompactFile`) shadowed it and the job failed at
configuration -- the name clash this unification removes.
