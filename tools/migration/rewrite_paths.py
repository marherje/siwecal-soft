#!/usr/bin/env python3
"""Rewrite repo-relative paths of the two old repos (in docs, comments, usage lines and literal paths) to their
siwecal-soft location, from MIGRATED.tsv. Only slash-containing paths are rewritten, longest first, and only where
they start a path token, so 'analysis/final_panels.py' (unchanged) or prose are left alone.

    python3 tools/migration/rewrite_paths.py [--apply]     # default: dry run, prints the counts per rule
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEXT = (".py", ".sh", ".md", ".sub", ".yml", ".yaml", ".txt", ".cpp", ".h", ".hh", ".xml", ".C", ".cfg", ".json")


def rules():
    files, dirs = {}, {}
    for line in open(os.path.join(ROOT, "tools", "migration", "MIGRATED.tsv")):
        f = line.rstrip("\n").split("\t")
        if len(f) != 3:
            continue
        _, old, new = f
        if old != new:
            files[old] = new
        # directory rules: old prefix P/ -> new prefix Q/ when the rest of the path is the same in both
        parts = old.split("/")
        for k in range(1, len(parts)):
            rest = "/".join(parts[k:])
            if new.endswith("/" + rest):
                dirs.setdefault("/".join(parts[:k]) + "/", set()).add(new[: -len(rest)])
    out = dict(files)
    for o, ns in dirs.items():
        # only unambiguous rules, and only for nested folders (a bare 'analysis/' or 'mappings/' stays a file rule)
        if len(ns) == 1 and o.count("/") >= 2:
            n = next(iter(ns))
            if n != o:
                out[o] = n
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    R = rules()
    R = {k: v for k, v in R.items() if "/" in k}
    keys = sorted(R, key=len, reverse=True)
    pat = re.compile(r"(?<![\w.-])(" + "|".join(re.escape(k) for k in keys) + r")")
    total = {}
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in (".git", "build", "install", ".venv") and not
                 os.path.join(dp, d).startswith(os.path.join(ROOT, "tools", "migration"))]
        for name in fn:
            if not name.endswith(TEXT):
                continue
            p = os.path.join(dp, name)
            try:
                s = open(p, encoding="utf-8").read()
            except UnicodeDecodeError:
                continue
            n = 0

            def sub(m):
                nonlocal n
                new = R[m.group(1)]
                # already the new path (e.g. 'common/' + 'mappings/x'): leave it
                if new.endswith(m.group(1)) and m.string[:m.start()].endswith(new[: -len(m.group(1))]):
                    return m.group(1)
                # after a slash only when that slash follows a variable or the old repo name: '${repo}/gaudi_jobs/..'
                if m.start() and m.string[m.start() - 1] == "/":
                    before = m.string[max(0, m.start() - 40):m.start() - 1]
                    if not re.search(r"(\}|\)|\$\w+|siwecal-tb2026|siwecal_k4sim|REPO|repo|ROOT|\bR|\bT|\bK)$", before):
                        return m.group(1)
                n += 1
                total[m.group(1)] = total.get(m.group(1), 0) + 1
                return R[m.group(1)]
            s2 = pat.sub(sub, s)
            if n and args.apply:
                open(p, "w", encoding="utf-8").write(s2)
    for k in sorted(total, key=lambda k: -total[k]):
        print(f"{total[k]:4d}  {k}  ->  {R[k]}")
    print(f"{sum(total.values())} replacements" + ("" if args.apply else " (dry run)"))


if __name__ == "__main__":
    sys.exit(main())
