#!/bin/bash
# siwecal_beamspot end to end: measure on a generated valtree, then tune and closure on hand-written JSON.
#   test_beamspot_exe.sh <path to siwecal_beamspot>
EXE=${1:?siwecal_beamspot}
D=$(mktemp -d "${TMPDIR:-/tmp}/beamspot_test.XXXXXX")
trap 'rm -rf "$D"' EXIT
fail() { echo "FAIL: $*"; exit 1; }

# 3000 events: 2000 shower-like (nhit 100) at x~N(5,10), y~N(-3,4); 1000 MIP-like (nhit 2) far away; and an empty
# tree. Written with uproot: a ROOT macro costs minutes of interpreter start-up on AFS.
python3 - "$D" <<'EOF' || fail "could not write the test valtrees"
import sys, numpy as np, uproot
d = sys.argv[1]
r = np.random.default_rng(7)
nhit = np.r_[np.full(2000, 100), np.full(1000, 2)].astype(np.int32)
x = np.r_[r.normal(5, 10, 2000), np.full(1000, 80.0)]
y = np.r_[r.normal(-3, 4, 2000), np.full(1000, 80.0)]
with uproot.recreate(f"{d}/v.root") as f:
    f["ecal"] = {"nhit_chan": nhit, "bar_x": x, "bar_y": y}
# expected values with numpy, the definition analysis/beam_spread.py uses
sel = nhit > 0.5 * np.percentile(nhit, 90)
w = lambda v: (np.percentile(v, 75) - np.percentile(v, 25)) / 1.349
import json
json.dump({"x": np.median(x[sel]), "y": np.median(y[sel]), "wx": w(x[sel]), "wy": w(y[sel]), "n": int(sel.sum())},
          open(f"{d}/expected.json", "w"))
with uproot.recreate(f"{d}/empty.root") as f:
    f["ecal"] = {"nhit_chan": np.zeros(0, np.int32), "bar_x": np.zeros(0), "bar_y": np.zeros(0)}
EOF

"$EXE" measure "$D/v.root" "$D/spot.json" || fail "measure exit code"
python3 - "$D/spot.json" <<'EOF' || fail "measure values"
import json, sys
s = json.load(open(sys.argv[1]))
e = json.load(open(sys.argv[1].replace("spot.json", "expected.json")))
assert s["n"] == e["n"] == 2000 and s["entries"] == 3000, (s, e)
assert all(abs(s[k] - e[k]) < 1e-9 for k in ("x", "y", "wx", "wy")), (s, e)
EOF

cat > "$D/data.json" <<'EOF'
{"run": "R", "data": {"x": 10, "y": 0, "wx": 12, "wy": 12, "n": 1000}, "gun0": {"x": 10, "y": 0, "sx": 12, "sy": 12}}
EOF
echo '{"x": 8, "y": 0, "wx": 13, "wy": 13, "n": 900}' > "$D/dummy.json"
"$EXE" tune "$D/data.json" "$D/dummy.json" "$D/params.json" || fail "tune exit code"
python3 - "$D/params.json" <<'EOF' || fail "tune values"
import json, math, sys
p = json.load(open(sys.argv[1]))
assert p["run"] == "R" and p["dummy"]["n"] == 900, p
assert abs(p["gun"]["x"] - 12) < 1e-9 and abs(p["gun"]["sx"] - math.sqrt(119)) < 1e-9, p
EOF

echo '{"x": 11.5, "y": 0, "wx": 12, "wy": 12, "n": 1000}' > "$D/sim.json"
"$EXE" closure "$D/params.json" "$D/sim.json" "$D/closure.json" || fail "closure exit code"
python3 - "$D/closure.json" <<'EOF' || fail "closure values"
import json, sys
c = json.load(open(sys.argv[1]))
assert abs(c["dx"] - 1.5) < 1e-9 and c["flag"] is True and c["sim"]["n"] == 1000, c
EOF

# an empty selection gives null values, not a crash
"$EXE" measure "$D/empty.root" "$D/empty.json" || fail "measure on an empty tree"
python3 -c "import json,sys; s=json.load(open('$D/empty.json')); assert s['n']==0 and s['x'] is None, s" || fail "empty values"

"$EXE" measure "$D/nope.root" "$D/x.json" 2>/dev/null && fail "missing input must fail"
echo OK
