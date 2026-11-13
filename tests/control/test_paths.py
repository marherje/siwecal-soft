"""Path resolution: every file the chains read is found through siwecal_common.paths, from any working directory,
and every Gaudi steering file a driver points at exists."""
import os
import re
import subprocess
import sys

import pytest

from conftest import ROOT


def _paths():
    sys.path.insert(0, os.path.join(ROOT, "common", "python"))
    from siwecal_common import paths
    return paths


def test_repo_root_and_mappings():
    paths = _paths()
    assert os.path.samefile(paths.REPO_ROOT, ROOT)
    assert os.path.samefile(paths.mappings_dir(), os.path.join(ROOT, "common", "mappings"))
    for f in ("slab_z_positions.yml", "digi_calibration.yml", "mip_values_sim.yml", "Tungsten_thickness.yml",
              "fev10_rotate_chip_channel_x_y_mapping.txt", "fev11_cob_good_rotate_chip_channel_x_y_mapping.txt"):
        assert os.path.isfile(paths.mapping_file(f)), f
    assert os.path.isdir(paths.configs_dir()), paths.configs_dir()


def test_occupancy_sag_tables_of_every_set_exist():
    import yaml
    paths = _paths()
    cal = yaml.safe_load(open(paths.mapping_file("digi_calibration.yml")))["thresholds"]
    for th, entry in cal.items():
        sag = entry.get("occupancy_sag_table")
        if sag:
            assert os.path.isfile(paths.mapping_file(sag)), f"{th}: {sag}"


def test_cli_from_another_directory(tmp_path):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "common", "python") + os.pathsep + os.environ.get("PYTHONPATH", ""))
    env.pop("SIWECAL_SOFT_ROOT", None)
    out = subprocess.run([sys.executable, "-m", "siwecal_common", "mappings_dir"], cwd=tmp_path, env=env,
                         capture_output=True, text=True, check=True)
    assert os.path.samefile(out.stdout.strip(), os.path.join(ROOT, "common", "mappings"))
    assert not out.stderr, out.stderr


def test_official_calibration_tree(eos):
    paths = _paths()
    mc = paths.muon_calib_dir()
    for kind in ("pedestals", "mips", "anchor"):
        for th in ("th210", "th220", "th230"):
            assert os.path.isdir(os.path.join(mc, kind, th)), os.path.join(mc, kind, th)


def test_steering_files_referenced_by_drivers_exist():
    """Every '<area>/options/<file>.py' or 'simulation/jobs/<file>.py' written in a driver or a launcher exists."""
    pat = re.compile(r"(data_conversion/options|reconstruction/(?:pid|tracking)/options|simulation/jobs)/(\w+\.py)")
    pat_join = re.compile(r'options_file\("([\w/]+)", "(\w+\.py)"\)')
    bad = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in (".git", "build", "install", "work", "docs", "tools")]
        for n in fn:
            if not n.endswith((".py", ".sh")):
                continue
            text = open(os.path.join(dp, n), errors="replace").read()
            for m in pat.finditer(text):
                if not os.path.isfile(os.path.join(ROOT, m.group(1), m.group(2))):
                    bad.append(f"{os.path.relpath(os.path.join(dp, n), ROOT)}: {m.group(0)}")
            for m in pat_join.finditer(text):
                if not os.path.isfile(os.path.join(ROOT, m.group(1), "options", m.group(2))):
                    bad.append(f"{os.path.relpath(os.path.join(dp, n), ROOT)}: {m.group(0)}")
    assert not bad, "\n".join(bad)
