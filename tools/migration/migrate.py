#!/usr/bin/env python3
"""One-off copy of the two frozen repos into the siwecal-soft tree, driven by layout.tsv.

Every file tracked at the pinned commit of each source repo must match a row of layout.tsv: it is either copied to
its destination or left out on purpose ('-'). A tracked file no row covers stops the migration, so nothing is lost
silently. Only tracked files are read (git archive), so build products, core dumps and private notes never enter.
Notebooks are copied with their outputs cleared.

    python3 tools/migration/migrate.py <dest> [--k-repo PATH] [--t-repo PATH] [--k-ref REF] [--t-ref REF]

Writes <dest>/tools/migration/MIGRATED.tsv (source -> destination of every file) and EXCLUDED.tsv.
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tarfile

HERE = os.path.dirname(os.path.abspath(__file__))


def read_layout(path):
    rows = []
    for line in open(path):
        if not line.strip() or line.startswith("#"):
            continue
        repo, src, dst = line.rstrip("\n").split("\t")
        rows.append((repo, src, dst))
    return rows


def destination(rows, repo, path):
    """A row matches its exact path, or any path it is a prefix of (a directory 'a/b/' or a name stem 'a/condor_')."""
    for r, src, dst in rows:
        if r == repo and path.startswith(src):
            return None if dst == "-" else dst + path[len(src):]
    raise KeyError(path)


def clear_notebook(data):
    nb = json.loads(data)
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    return (json.dumps(nb, indent=1, ensure_ascii=False) + "\n").encode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dest")
    ap.add_argument("--k-repo", default="/afs/cern.ch/user/m/marquezh/public/siwecal_k4sim")
    ap.add_argument("--t-repo", default="/afs/cern.ch/user/m/marquezh/public/siwecal-tb2026")
    ap.add_argument("--k-ref", default="final-before-monorepo")
    ap.add_argument("--t-ref", default="final-before-monorepo")
    args = ap.parse_args()
    rows = read_layout(os.path.join(HERE, "layout.tsv"))
    migrated, excluded, missing = [], [], []
    for repo, root, ref in (("K", args.k_repo, args.k_ref), ("T", args.t_repo, args.t_ref)):
        sha = subprocess.check_output(["git", "-C", root, "rev-parse", ref + "^{commit}"], text=True).strip()
        tar = subprocess.check_output(["git", "-C", root, "archive", sha])
        with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                try:
                    dst = destination(rows, repo, m.name)
                except KeyError:
                    missing.append(f"{repo}\t{m.name}")
                    continue
                if dst is None:
                    excluded.append(f"{repo}@{sha[:7]}\t{m.name}")
                    continue
                data = tf.extractfile(m).read()
                if m.name.endswith(".ipynb"):
                    data = clear_notebook(data)
                out = os.path.join(args.dest, dst)
                if os.path.exists(out):
                    sys.exit(f"collision: {repo}:{m.name} -> {dst} already written")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with open(out, "wb") as f:
                    f.write(data)
                os.chmod(out, m.mode & 0o777 | 0o600)
                migrated.append(f"{repo}@{sha[:7]}\t{m.name}\t{dst}")
    if missing:
        sys.exit("tracked files that no layout.tsv row covers:\n  " + "\n  ".join(missing))
    log = os.path.join(args.dest, "tools", "migration")
    os.makedirs(log, exist_ok=True)
    open(os.path.join(log, "MIGRATED.tsv"), "w").write("\n".join(migrated) + "\n")
    open(os.path.join(log, "EXCLUDED.tsv"), "w").write("\n".join(excluded) + "\n")
    print(f"{len(migrated)} files copied, {len(excluded)} left out (tools/migration/EXCLUDED.tsv)")


if __name__ == "__main__":
    main()
