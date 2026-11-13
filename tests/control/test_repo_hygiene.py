"""The repo stays clean and self-contained (runs without key4hep: also in the GitHub CI).

  - no personal paths (an AFS home, a personal EOS area) and no reference to the two retired repos as a location
    (../siwecal-tb2026, TB_REPO, gaudi_source/build, genConfDir, init_key4hep.sh, masking_info/);
  - sys.path is only extended inside a folder of script modules, never to reach another part of the repo or another
    checkout (the packages come from init_siwecalsoft.sh / pyproject.toml);
  - no data, table or output is versioned: no file over 1 MB, no ROOT/npz/png outputs, no condor products;
  - the mappings exist once, in common/mappings.
"""
import os
import re

import pytest

from conftest import ROOT, tracked_files

TEXT = (".py", ".sh", ".sub", ".yml", ".yaml", ".cpp", ".h", ".hh", ".C", ".xml", ".txt", ".cfg", ".toml", ".json")
# Prose may name the retired repos (history, docs); these patterns are locations, i.e. bugs waiting to happen.
FORBIDDEN = {
    "personal AFS path": re.compile(r"/afs/cern\.ch/user/"),
    "personal EOS path": re.compile(r"/eos/user/[a-z]/\w+"),
    "DESY personal path": re.compile(r"/nfs/dust/\w+/user/"),
    "sibling checkout": re.compile(r"\.\./siwecal[-_](tb2026|k4sim)"),
    "TB_REPO / TB2026_ROOT": re.compile(r"\b(TB_REPO|TB2026_ROOT|K4RECO_BUILD)\b"),
    "old build tree": re.compile(r"gaudi_source/build|genConfDir"),
    "old environment script": re.compile(r"init_key4hep\.sh|init_siwecal_soft\.sh|source setup\.sh"),
    "old calibration copy": re.compile(r"masking_info/|calibration/MuonCalib_(gaudi|it2)|\"calibration\", \"MuonCalib"),
}
# legitimate uses: the xrdcp stage-out picks the EOS instance from the destination prefix
ALLOWED = {("personal EOS path", "simulation/run/sim_digi_chunk.sh"), ("personal EOS path", "simulation/run/ddsim_beam_chunk.sh"),
           # the migration check runs the frozen siwecal_k4sim in its own environment, on purpose
           ("old environment script", "tools/validation/run_v9_plots.sh")}
SYS_PATH_OK = re.compile(r"sys\.path\.insert\(0, (os\.path\.join\()?(_HERE|_SCRIPT_DIR|os\.path\.dirname\(os\.path\.abspath\(__file__\)\)|"
                         r"str\(GEOMETRY_DIR\)|str\(Path\(__file__\)|DISPLAY_DIR|GEOM_DIR|REPO_ROOT\b)")


def _source_files():
    for rel in tracked_files(ROOT):
        if rel.startswith(("docs/", "tools/migration/", "tests/control/")) or not rel.endswith(TEXT):
            continue
        yield rel


def test_no_personal_or_retired_repo_paths():
    bad = []
    for rel in _source_files():
        text = open(os.path.join(ROOT, rel), errors="replace").read()
        for what, pat in FORBIDDEN.items():
            if (what, rel) in ALLOWED:
                continue
            for m in pat.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                bad.append(f"{rel}:{line}: {what}: {m.group(0)}")
    assert not bad, "\n".join(bad)


def test_sys_path_only_for_sibling_script_modules():
    bad = []
    for rel in _source_files():
        if not rel.endswith(".py"):
            continue
        for i, line in enumerate(open(os.path.join(ROOT, rel), errors="replace"), 1):
            if "sys.path.insert" in line and not SYS_PATH_OK.search(line):
                bad.append(f"{rel}:{i}: {line.strip()}")
            if "sys.path.insert" in line and re.search(r"siwecal-tb2026|siwecal_k4sim|\.\./\.\.", line):
                bad.append(f"{rel}:{i}: {line.strip()}")
    assert not bad, "\n".join(bad)


def test_no_data_or_outputs_versioned():
    big, outputs = [], []
    for rel in tracked_files(ROOT):
        p = os.path.join(ROOT, rel)
        if rel.startswith("tools/migration/"):
            continue
        if os.path.getsize(p) > 1_000_000:
            big.append(f"{rel} ({os.path.getsize(p) / 1e6:.1f} MB)")
        if rel.endswith((".root", ".npz", ".npy", ".png", ".pdf", ".slcio", ".dag", ".metrics")) or \
                re.search(r"(^|/)(condor_[^/]+|out_[^/]+)/", rel) or re.search(r"(^|/)core\.\d+$", rel):
            outputs.append(rel)
    assert not big, "files over 1 MB:\n" + "\n".join(big)
    assert not outputs, "outputs in the tree:\n" + "\n".join(outputs)


def test_mappings_exist_once():
    names = {"slab_z_positions.yml", "Tungsten_thickness.yml", "fev10_rotate_chip_channel_x_y_mapping.txt",
             "fev11_cob_good_rotate_chip_channel_x_y_mapping.txt", "digi_calibration.yml"}
    found = {}
    for rel in tracked_files(ROOT):
        if os.path.basename(rel) in names:
            found.setdefault(os.path.basename(rel), []).append(rel)
    assert set(found) == names, f"missing: {names - set(found)}"
    dup = {k: v for k, v in found.items() if v != [f"common/mappings/{k}"]}
    assert not dup, f"mapping files outside common/mappings: {dup}"


def test_notebooks_have_no_outputs():
    import json
    bad = []
    for rel in tracked_files(ROOT):
        if rel.endswith(".ipynb"):
            nb = json.load(open(os.path.join(ROOT, rel)))
            if any(c.get("outputs") for c in nb.get("cells", []) if c.get("cell_type") == "code"):
                bad.append(rel)
    assert not bad, f"notebooks saved with outputs: {bad}"


def test_no_set_u_around_the_environment():
    """key4hep's setup dies under `set -u` (silently, in batch): a script that turns on nounset must switch it off
    around every `source` of init_siwecalsoft.sh or of the key4hep setup in its own shell (heredocs, i.e. generated
    wrappers, are checked as their own text)."""
    bad = []
    for rel in tracked_files(ROOT):
        if not rel.endswith(".sh") or rel.startswith("tools/migration/"):
            continue
        nounset, heredoc = False, None
        for i, line in enumerate(open(os.path.join(ROOT, rel), errors="replace"), 1):
            s = line.strip()
            if heredoc:
                if s == heredoc:
                    heredoc = None
                continue
            m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", s)
            if m and not s.startswith("#"):
                heredoc = m.group(1)
                continue
            if "set +u" in s and "source" in s:      # 'set +u; source ...; set -u' on one line: wrapped
                continue
            if re.match(r"set \+u", s):
                nounset = False
            elif re.match(r"set -[a-z]*u", s):
                nounset = True
            if nounset and not s.startswith("#") and re.search(r"\bsource\b.*(init_siwecalsoft\.sh|key4hep/setup\.sh)", s):
                bad.append(f"{rel}:{i}: {s}")
    assert not bad, "\n".join(bad)
