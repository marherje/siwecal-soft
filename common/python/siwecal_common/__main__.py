"""Shell access to siwecal_common.paths:   python3 -m siwecal_common <key>   (e.g. calib_dir, muon_calib_dir)."""
import sys

from siwecal_common.paths import _CLI

if len(sys.argv) != 2 or sys.argv[1] not in _CLI:
    sys.exit("usage: python3 -m siwecal_common {" + ",".join(sorted(_CLI)) + "}")
print(_CLI[sys.argv[1]]())
