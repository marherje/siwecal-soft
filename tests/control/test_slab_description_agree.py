"""common/mappings/slab_z_positions.yml has one reader, siwecal_common.slab_description (the two former repos had one
each); siwecal_eventbuilder.geometry.load_slab_technology returns it in the data-side shape for the event builder,
the reco DAG and the viewer. Both views must describe every slab identically."""
import os
import sys

from conftest import ROOT

sys.path[:0] = [os.path.join(ROOT, "common", "python"), os.path.join(ROOT, "data_conversion", "python")]


def test_sim_and_data_readers_agree_on_every_slab():
    from siwecal_common import paths
    from siwecal_common.slab_description import load_slab_description
    from siwecal_eventbuilder.geometry import load_slab_technology
    y = paths.mapping_file("slab_z_positions.yml")
    sim, data = load_slab_description(y), load_slab_technology(y, paths.mappings_dir())
    assert list(sim.technology) == list(data.technology)
    assert list(sim.sensor_thickness_um) == list(data.sensor_thickness_um)
    assert [os.path.realpath(p) for p in sim.pad_map] == [os.path.realpath(p) for p in data.pad_map]
    assert list(sim.threshold_dac) == list(data.threshold_dac)
    assert os.path.realpath(sim.default_pad_map()) == os.path.realpath(data.default_pad_map())
    assert {k: os.path.realpath(v) for k, v in sim.pad_map_overrides().items()} == \
           {k: os.path.realpath(v) for k, v in data.pad_map_overrides().items()}
