#!/usr/bin/env python3
"""Compare the text outputs of tools/validation/run_v9_plots.sh old vs new (and optionally a third tree, e.g. the
published border_cut/figs_v9_setcal): every *.txt present in both trees must be identical, numbers included; the
figures are listed (pixel comparison is not meaningful across matplotlib runs, the numbers they show are in the txt).

    python3 tools/validation/compare_v9_outputs.py <old_dir> <new_dir>
"""
import difflib
import os
import sys


def texts(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(("cache_", "."))]
        for n in fn:
            if n.endswith(".txt"):
                out[os.path.relpath(os.path.join(dp, n), root)] = os.path.join(dp, n)
    return out


def main():
    a, b = sys.argv[1], sys.argv[2]
    ta, tb = texts(a), texts(b)
    bad = 0
    for k in sorted(set(ta) | set(tb)):
        if k not in ta or k not in tb:
            print(f"ONLY IN {'old' if k in ta else 'new'}: {k}")
            bad += 1
            continue
        la, lb = open(ta[k]).read().splitlines(), open(tb[k]).read().splitlines()
        # titles may carry the checkout path; everything else must match
        if la == lb:
            print(f"identical  {k}")
            continue
        bad += 1
        print(f"DIFFERS    {k}")
        for line in list(difflib.unified_diff(la, lb, "old", "new", lineterm="", n=0))[:20]:
            print("    " + line)
    pngs = sum(1 for _, _, fn in os.walk(b) for n in fn if n.endswith(".png"))
    print(f"\n{len(set(ta) & set(tb))} text outputs compared, {bad} differ; {pngs} figures in {b}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
