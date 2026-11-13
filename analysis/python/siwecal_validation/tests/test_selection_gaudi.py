"""CutSet -> EcalEventSelection properties (run_pid_batch.py): every cut variable is an EcalShowerVars scalar, and
the bounds survive the string round trip exactly."""
import os
import re

from siwecal_common import edm4hep_pid
from siwecal_validation.selection import CutSet, _CUT_SPEC

_HEADER = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "reconstruction", "pid", "include",
                       "siwecal", "EcalShowerVars.h")


def _cpp_scalar_names():
    text = open(_HEADER).read()
    body = text[text.index("scalarNames()"):]
    body = body[body.index("{", body.index("names")):body.index("};")]
    return re.findall(r'"([a-z0-9_]+)"', body)


def test_every_cut_variable_is_a_cpp_scalar():
    names = _cpp_scalar_names()
    assert names == list(edm4hep_pid.SCALAR_NAMES)
    assert {attr for *_, attr in _CUT_SPEC} <= set(names)


def test_empty_cutset_has_no_gaudi_cuts():
    assert CutSet().gaudi_cuts() == [] and CutSet().gaudi_is_shower == -1


def test_gaudi_cuts_open_bounds_and_exact_values():
    cut = CutSet(moliere_min=30, weighte_max=4000, border_min=0.1, border_max=1 / 3, is_shower=True)
    specs = cut.gaudi_cuts()
    assert specs == ["weighte::4000.0", "moliere:30.0:", f"barxy_min_border_distance:0.1:{1 / 3!r}"]
    assert float(specs[2].split(":")[2]) == 1 / 3
    assert cut.gaudi_is_shower == 1 and CutSet(is_shower=False).gaudi_is_shower == 0


def test_merged_yaml_cut_overrides_cli():
    merged = CutSet(moliere_min=30, nhit_min=5).merge(CutSet.from_mapping({"moliere_min": 45}))
    assert merged.gaudi_cuts() == ["nhit:5.0:", "moliere:45.0:"]
