"""
Reader for the EDM4hep output of ``SiWEcalPID`` (the Gaudi PID stage).

The PID job writes one podio event (Frame) per physics event with:

* ``ECalHits``    -- an ``edm4hep::CalorimeterHitCollection`` (per-hit energy,
  position, cellID), the EDM4hep replacement for the old per-hit ``hit_*``
  branches of the ``ecal`` tree.
* ``ECalPid``     -- an ``edm4hep::ClusterCollection`` with exactly one Cluster
  per event whose ``shapeParameters`` hold every per-event discrimination
  variable (the old ``*.valcache.root`` derived branches). The names are stored
  once in the ``metadata`` frame parameter ``ECalPid_shapeParameterNames``.
* ``EventHeader`` -- run / event numbers (+ bcid in ``timeStamp``, spill in
  ``weight``).

This is the single source of truth both ``siwecal_validation`` and
``event_viewer`` use to read EDM4hep, so neither recomputes the metrics: they are
read straight from the Cluster (computed in C++ by ``EcalShowerVariables``).
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

SHAPE_PARAM_META = "ECalPid_shapeParameterNames"
IDENTIFIER_COLUMNS = ("run", "event", "spill", "bcid", "nhit_chan")

# Canonical shapeParameters layout -- mirror of siwecal/EcalShowerVars.h
# (scalarNames / perLayerNames) and EcalShowerVariables's MIP-cut prefixes. Kept
# in Python so opening a file needs no podio call (the slow part); the actual
# width is asserted against the file in PidFileReader._build_scalars.
SCALAR_NAMES = (
    "nhit", "zbary", "energy", "mip_likeness", "weighte", "bar_x", "bar_y", "bar_r",
    "moliere", "transverse_rms", "is_shower", "shower_start", "shower_max", "shower_end",
    "shower_start_10", "shower_end_10", "shower_length", "first_layer", "last_layer",
    "n_layers_hit", "e_over_nhit",
    # Appended, not interleaved with the shower_* block: the index of every
    # pre-existing scalar has to stay put. Mirrors scalarNames() in
    # siwecal/EcalShowerVars.h, which is the source of truth.
    "shower_onset", "n_layers_before_onset",
    "fractal_dimension",
    "barxy_min_border_distance")
PER_LAYER_NAMES = ("hits_per_layer", "energy_per_layer", "weighte_per_layer")
_MIP_PREFIX = {0.5: "mip05", 1.0: "mip1"}


def canonical_shape_names(n_layers: int = 15, mip_thresholds=(0.5, 1.0)) -> List[str]:
    """The ordered shapeParameter names written by ``EcalShowerVariables``."""
    names = list(SCALAR_NAMES)
    for block in PER_LAYER_NAMES:
        names += [f"{block}_{i}" for i in range(n_layers)]
    for thr in mip_thresholds:
        names += [f"{_MIP_PREFIX[thr]}_{s}" for s in SCALAR_NAMES]
    return names
# Per-hit fields exposed under the legacy ``hit_*`` names (so downstream is
# unchanged). slab/x/y/z/energy come from the CalorimeterHit; the rest from the
# parallel podio UserDataCollections written by EcalToEDM4hep.
PERHIT_FIELDS = ("hit_slab", "hit_x", "hit_y", "hit_z", "hit_energy",
                 "hit_chip", "hit_chan", "hit_sca", "hit_hg", "hit_lg",
                 "hit_w_energy", "hit_X0")

# Legacy hit field -> (collection name, numpy dtype) for the UserDataCollections.
_USERDATA_HITS = {
    "hit_chip": ("ECalHitChip", np.int32),
    "hit_chan": ("ECalHitChan", np.int32),
    "hit_sca": ("ECalHitSca", np.int32),
    "hit_hg": ("ECalHitHG", np.float32),
    "hit_lg": ("ECalHitLG", np.float32),
    "hit_w_energy": ("ECalHitWE", np.float32),
    "hit_X0": ("ECalHitX0", np.float32),
}

# Fields whose UserDataCollection postdates the earliest PID files. A file
# written before them is still perfectly readable -- the field is dropped from
# :meth:`PidFileReader.perhit_fields` rather than faked, so a consumer can tell
# "not recorded" from a real value. Everything else is mandatory: its absence is
# a corrupt file, not an old one, and should raise.
OPTIONAL_PERHIT_FIELDS = ("hit_w_energy", "hit_X0")


class PidFileReader:
    """Lazy reader over one EDM4hep PID file (``ECalHits`` + ``ECalPid``)."""

    def __init__(self, path: str, events_coll: str = "ECalPid",
                 hits_coll: str = "ECalHits", header_coll: str = "EventHeader",
                 n_layers: int = 15, mip_thresholds=(0.5, 1.0)):
        self.path = path
        self._events_coll = events_coll
        self._hits_coll = hits_coll
        self._header_coll = header_coll

        # Names from the Python schema -> opening a file does no podio work.
        self._n_layers = n_layers
        self.shape_names: List[str] = canonical_shape_names(n_layers, mip_thresholds)
        self._name_idx = {n: i for i, n in enumerate(self.shape_names)}

        self._reader = None
        self._frames_cache = None
        self._scalars: Optional[np.ndarray] = None   # (n_events, n_shape_params)
        self._ids: Optional[Dict[str, np.ndarray]] = None
        self._hits: Optional[Dict[str, np.ndarray]] = None  # jagged object arrays
        self._fields: Optional[tuple] = None         # PERHIT_FIELDS minus absent optionals
        self._track_z_table: Optional[np.ndarray] = None
        self._track_z_table_built = False
        self._track_counts: Optional[np.ndarray] = None
        self._track_counts_built = False

    @property
    def _frames(self):
        """podio frames, created lazily (only needed for per-hit access)."""
        if self._frames_cache is None:
            import podio.root_io as rio  # heavy: defer until a hit read is needed
            self._reader = rio.Reader(self.path)
            self._frames_cache = self._reader.get("events")
        return self._frames_cache

    # ----------------------------------------------------------- metadata ----
    @property
    def n_events(self) -> int:
        if self._scalars is None:
            self._build_scalars()
        return self._scalars.shape[0]

    def has_param(self, name: str) -> bool:
        return name in self._name_idx

    # ------------------------------------------------- per-event scalars -----
    def _build_scalars(self) -> None:
        """Vectorised read of the per-event scalars with uproot.

        The podio TTree stores the Cluster ``shapeParameters`` of all events in a
        single flat branch (one cluster per event -> a regular ``(n, n_params)``
        block) and the ``EventHeader`` fields as length-1 jagged branches.
        Reading them columnar with uproot is far faster than looping the podio
        frames in Python (which is what made the viewer slow to load).
        """
        import awkward as ak
        import uproot

        tree = uproot.open(self.path)["events"]
        ev = self._events_coll
        sp = tree[f"_{ev}_shapeParameters"].array()
        mat = ak.to_numpy(sp)                      # regular: 1 cluster/event
        if mat.shape[1] != len(self.shape_names):
            # The width can differ from the compiled-in canonical layout for
            # more than one reason: physics-mode files (no mip05_/mip1_
            # variant blocks), or an older EcalShowerVariables that predates a
            # later addition to SCALAR_NAMES (e.g. shower_onset/
            # n_layers_before_onset, added after some real-data PID files were
            # already written). The file's own metadata frame parameter
            # (SHAPE_PARAM_META) is its authoritative record of what it
            # actually wrote -- read that instead of guessing a variant.
            names = self._shape_names_from_metadata()
            if names is not None and len(names) == mat.shape[1]:
                self.shape_names = names
                self._name_idx = {n: i for i, n in enumerate(names)}
            else:
                base = canonical_shape_names(self._n_layers, mip_thresholds=())
                if mat.shape[1] == len(base):
                    self.shape_names = base
                    self._name_idx = {n: i for i, n in enumerate(base)}
                else:
                    raise RuntimeError(
                        f"shapeParameters width {mat.shape[1]} != "
                        f"{len(self.shape_names)} names in {self.path}, and "
                        f"{SHAPE_PARAM_META} metadata did not resolve it either")

        hd = self._header_coll
        first = lambda field: ak.to_numpy(  # noqa: E731
            ak.firsts(tree[f"{hd}/{hd}.{field}"].array()))
        self._scalars = mat.astype(float)
        self._ids = {
            "run": first("runNumber").astype(np.int64),
            "event": first("eventNumber").astype(np.int64),
            "bcid": first("timeStamp").astype(np.int64),
            "spill": first("weight").astype(np.int64),
            # nhit (cluster) == number of ECalHits == legacy nhit_chan.
            "nhit_chan": mat[:, self._name_idx["nhit"]].astype(np.int64),
        }

    def _shape_names_from_metadata(self) -> Optional[List[str]]:
        """The file's own :data:`SHAPE_PARAM_META` list, or ``None`` if it
        cannot be read (very old file, or no ``metadata`` category)."""
        try:
            import podio.root_io as rio

            reader = rio.Reader(self.path)
            for frame in reader.get("metadata"):
                raw = frame.get_parameter(SHAPE_PARAM_META)
                return [n.decode("utf-8") if isinstance(n, bytes) else str(n) for n in raw]
        except Exception:
            return None
        return None

    def scalar(self, name: str) -> np.ndarray:
        """Per-event array of one shape-parameter (e.g. ``moliere``)."""
        if self._scalars is None:
            self._build_scalars()
        return self._scalars[:, self._name_idx[name]]

    def identifiers(self) -> Dict[str, np.ndarray]:
        if self._ids is None:
            self._build_scalars()
        return self._ids

    def scalar_columns(self, names: Optional[List[str]] = None) -> Dict[str, np.ndarray]:
        """Dict ``name -> per-event array`` for the requested shape-parameters
        (default: all of them), plus the identifier columns."""
        if self._scalars is None:
            self._build_scalars()
        names = names if names is not None else self.shape_names
        out = {n: self._scalars[:, self._name_idx[n]] for n in names if n in self._name_idx}
        out.update(self.identifiers())
        return out

    # ------------------------------------------------------- per-hit ---------
    def perhit_fields(self) -> tuple:
        """The ``PERHIT_FIELDS`` this file carries, in canonical order.

        Equal to ``PERHIT_FIELDS`` for a file written by the current
        ``EcalToEDM4hep``; an older file drops whichever of
        :data:`OPTIONAL_PERHIT_FIELDS` its writer did not know about.
        """
        if self._fields is None:
            available = set(self._frames[0].getAvailableCollections()) if len(self._frames) else set()
            self._fields = tuple(
                f for f in PERHIT_FIELDS
                if f not in OPTIONAL_PERHIT_FIELDS or _USERDATA_HITS[f][0] in available)
        return self._fields

    def read_hits(self, index: int) -> Dict[str, np.ndarray]:
        """Per-hit arrays for a single event, keyed by :meth:`perhit_fields`."""
        fields = self.perhit_fields()
        frame = self._frames[index]
        hits = frame.get(self._hits_coll)
        m = len(hits)
        slab = np.empty(m, np.int32)
        x = np.empty(m, np.float32)
        y = np.empty(m, np.float32)
        z = np.empty(m, np.float32)
        energy = np.empty(m, np.float32)
        for j, hit in enumerate(hits):
            pos = hit.getPosition()
            x[j], y[j], z[j] = pos.x, pos.y, pos.z
            energy[j] = hit.getEnergy()
            slab[j] = hit.getType()   # layer stored natively in CalorimeterHit.type
        out = {"hit_slab": slab, "hit_x": x, "hit_y": y, "hit_z": z, "hit_energy": energy}
        # Parallel per-hit UserDataCollections (same order as the hits).
        for field, (coll_name, dtype) in _USERDATA_HITS.items():
            if field not in fields:
                continue
            coll = frame.get(coll_name)
            out[field] = np.fromiter(coll, dtype=dtype, count=len(coll))
        return out

    def all_hits(self) -> Dict[str, np.ndarray]:
        """All events' per-hit arrays as jagged object arrays (cached)."""
        if self._hits is None:
            fields = self.perhit_fields()
            n = len(self._frames)
            store = {f: np.empty(n, dtype=object) for f in fields}
            for i in range(n):
                hits = self.read_hits(i)
                for f in fields:
                    store[f][i] = hits[f]
            self._hits = store
        return self._hits

    # ------------------------------------------------------- ACTS tracks -----
    def track_counts(self) -> Optional[np.ndarray]:
        """Per-event ``ACTSTracks`` count, or ``None`` if the file has none.

        Simulation PID files get ``ACTSTracks`` merged straight in by the
        PID job (``run_pid.py`` ``PID_MERGE_FILE``; see ``docs/sim/gaudi_pipeline.md``,
        "Single-file output"); real test-beam PID files never have the
        collection, which is not an error -- just nothing to report.
        """
        if not self._track_counts_built:
            self._track_counts_built = True
            try:
                import awkward as ak
                import uproot

                tree = uproot.open(self.path)["events"]
                branch = "ACTSTracks/ACTSTracks.chi2"
                if branch in tree.keys():
                    self._track_counts = ak.to_numpy(
                        ak.num(tree[branch].array())).astype(np.int64)
            except Exception:
                self._track_counts = None
        return self._track_counts

    def track_z_table(self) -> Optional[np.ndarray]:
        """Sorted, unique ``AtOther`` track-state z values across the whole
        file, or ``None`` if it has no ACTSTracks states at all.

        This is the detector's per-slab z table in WHATEVER frame
        ``ACTSTracks`` was actually written in: for simulation, job4_tracking
        runs on the pre-flip ``SiPadHitsDigi`` (see "Use the PRE-flip
        collection" in ``docs/gaudi_pipeline.md``), so ``referencePoint.z``
        comes out in the DD4hep/simulation frame (positive, ~49-274 mm) even
        though ``ECalHits`` in this SAME file are already in the test-beam
        frame (``SiPadHitsMapped``, negative, 0..-225 mm) -- two different z
        conventions in one file. Real test-beam ACTSTracks have no such
        mismatch (``ACTSGeoSvc`` in slabz mode builds its surfaces straight from
        ``common/mappings/slab_z_positions.yml``), so this table already matches
        the hits there and callers should treat a non-positive table as
        "nothing to remap". One uproot scan, cached.
        """
        if not self._track_z_table_built:
            self._track_z_table_built = True
            try:
                import awkward as ak
                import uproot

                tree = uproot.open(self.path)["events"]
                branch = "_ACTSTracks_trackStates/_ACTSTracks_trackStates.referencePoint.z"
                loc_branch = "_ACTSTracks_trackStates/_ACTSTracks_trackStates.location"
                if branch in tree.keys():
                    z = ak.flatten(tree[branch].array())
                    loc = ak.flatten(tree[loc_branch].array())
                    z_other = ak.to_numpy(z[loc != 1])  # drop the AtIP placeholder
                    if z_other.size:
                        self._track_z_table = np.unique(np.round(z_other, 1))
            except Exception:
                self._track_z_table = None
        return self._track_z_table

    def read_tracks(self, index: int) -> List[dict]:
        """Track state points for one event, ``[]`` if there are none.

        Each dict is ``{"points": [(x,y,z), ...], "chi2": float, "ndf": int}``
        -- only the ``AtOther`` states (one per detector surface, in the same
        detector frame as the hits), sorted by z. The ``AtIP`` state's
        ``referencePoint`` is a ``(0,0,0)`` placeholder (its seed position
        lives in ``D0``/``Z0`` instead) and is excluded from the polyline.
        """
        try:
            # Keep an explicit reference to the Frame: an unnamed
            # self._frames[index].get(...) chained in one expression let the
            # Frame's refcount drop to zero once the statement finished,
            # leaving Track/TrackState access into freed memory -- crashed
            # inside edm4hep::TrackMutableCollectionIterator::operator*()
            # on the very next call (the same bug once hit an unbound podio
            # Reader temporary).
            frame = self._frames[index]
            tracks_coll = frame.get("ACTSTracks")
        except Exception:
            return []
        out = []
        for t in tracks_coll:
            pts = []
            for s in t.getTrackStates():
                if s.location == 1:  # AtIP: placeholder referencePoint, skip
                    continue
                rp = s.referencePoint
                pts.append((float(rp.x), float(rp.y), float(rp.z)))
            pts.sort(key=lambda p: p[2])
            out.append({"points": pts, "chi2": float(t.getChi2()), "ndf": int(t.getNdf())})
        return out

    def close(self) -> None:
        # podio Reader has no explicit close; drop references.
        self._frames = None
