"""
The EDM4hep PID reader of the event viewer: :class:`siwecal_common.edm4hep_pid.PidFileReader` (one implementation,
shared with the PID drivers and the validation) plus the viewer's fast whole-file hit read -- columnar with uproot,
falling back to the per-hit podio loop -- which the accumulated scenes need. (siwecal-tb2026 kept a private copy of
the whole module here; the copy and the original had drifted apart.)
"""
from typing import Dict

import numpy as np

from siwecal_common.edm4hep_pid import (OPTIONAL_PERHIT_FIELDS, PERHIT_FIELDS, _USERDATA_HITS,  # noqa: F401
                                        PidFileReader as _SharedPidFileReader, canonical_shape_names)


class PidFileReader(_SharedPidFileReader):
    """:class:`siwecal_common.edm4hep_pid.PidFileReader` with a columnar :meth:`all_hits`."""

    def all_hits(self) -> Dict[str, np.ndarray]:
        """All events' per-hit arrays as jagged object arrays (cached).

        This is the dominant cost of the per-cluster accumulated scenes. It is read
        columnar with uproot -- the ``CalorimeterHit`` position/energy/type and the
        parallel per-hit ``UserDataCollection``s are flat jagged branches, so one
        vectorised read of the whole file is ~40-100x faster than looping the podio
        frames hit-by-hit (which is what made this step take minutes on a full run).
        Falls back to the per-hit podio read if the columnar read fails.
        """
        if self._hits is not None:
            return self._hits
        from ._timing import logger, timed
        try:
            with timed("edm4hep all_hits (columnar uproot read)") as info:
                store, n, nhits = self._all_hits_columnar()
                self._hits = store
                info["events"] = n
                info["hits"] = nhits
        except Exception as exc:  # noqa: BLE001 - any read error -> safe fallback
            logger.warning("columnar all_hits failed (%s); falling back to "
                           "per-hit podio read", exc)
            self._hits = self._all_hits_podio()
        return self._hits

    def _all_hits_columnar(self):
        """``(store, n_events, n_hits)`` read columnar with uproot (the fast path).

        Each field is read as a jagged array, then split into one contiguous numpy
        sub-array per event (views into the flat content) so the return shape --
        ``{field: object-array of per-event arrays}`` -- matches the podio path.
        """
        import awkward as ak
        import uproot

        tree = uproot.open(self.path)["events"]
        hc = self._hits_coll
        # legacy field -> (branch, dtype); CalorimeterHit block + parallel UserData.
        spec = {
            "hit_slab": (f"{hc}/{hc}.type", np.int32),
            "hit_x": (f"{hc}/{hc}.position.x", np.float32),
            "hit_y": (f"{hc}/{hc}.position.y", np.float32),
            "hit_z": (f"{hc}/{hc}.position.z", np.float32),
            "hit_energy": (f"{hc}/{hc}.energy", np.float32),
        }
        # Availability is decided from the uproot branch list, not perhit_fields(),
        # so the fast path stays free of the podio frame load it exists to avoid.
        keys = set(tree.keys())
        spec.update({f: (coll, dt) for f, (coll, dt) in _USERDATA_HITS.items()
                     if f not in OPTIONAL_PERHIT_FIELDS or coll in keys})

        arrays = tree.arrays([b for b, _ in spec.values()], library="ak")
        counts = ak.to_numpy(ak.num(arrays[spec["hit_energy"][0]])).astype(np.int64)
        offsets = np.cumsum(counts)[:-1]
        store: Dict[str, np.ndarray] = {}
        for field, (branch, dtype) in spec.items():
            flat = ak.to_numpy(ak.flatten(arrays[branch])).astype(dtype, copy=False)
            parts = np.split(flat, offsets)          # per-event views, no copy
            obj = np.empty(len(parts), dtype=object)
            for i, part in enumerate(parts):
                obj[i] = part
            store[field] = obj
        return store, int(counts.size), int(counts.sum())

    def _all_hits_podio(self) -> Dict[str, np.ndarray]:
        """Fallback: read every event's hits through the podio frames.

        Slow (per-hit accessors) but dependency-light; logs periodic progress so a
        long read is visibly advancing rather than hung.
        """
        import time as _time
        from ._timing import progress, timed
        n = len(self._frames)
        fields = self.perhit_fields()
        with timed("edm4hep all_hits (per-hit podio read)") as info:
            store = {f: np.empty(n, dtype=object) for f in fields}
            t0 = _time.perf_counter()
            nhits = 0
            for i in range(n):
                hits = self.read_hits(i)
                nhits += int(hits["hit_x"].size)
                for f in fields:
                    store[f][i] = hits[f]
                if (i + 1) % 1000 == 0 or (i + 1) == n:
                    progress("all_hits", i + 1, n, t0, hits=nhits)
            info["events"] = n
            info["hits"] = nhits
        return store

    # ------------------------------------------------------- ACTS tracks -----
