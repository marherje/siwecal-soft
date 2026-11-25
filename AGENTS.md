# Rules for AI agents

They apply to every AI agent (Claude Code, Copilot, Codex, ...) working in this repository, and to its subagents.
The person using the agent is responsible for what it does.

## Git

- **Never commit, push, merge, tag or rewrite history.** Commits are made by hand, by a person who has reviewed every
  change. Propose the exact commands (`git add <files>`, `git commit -m "..."`) instead.
- List the files in `git add`; no `git add -A` or `git add .`.
- Small commits, descriptive messages in English, no AI co-author or attribution lines.
- Do not touch uncommitted changes that are not yours.

## Data

- **Never delete, move or overwrite anything on data storage** (EOS, dCache, DUST). If it seems needed, propose the
  command and let the person run it.
- Input files are read-only; outputs go to a new directory. Never into `Reconstruction/`, the decoded data
  (`rundata_converted_gaudi/`) or the calibration tables.
- `data_conversion/jobs/condor/generate_reco_dag.py` on runs that are already decoded: never run its CONVERT nodes, use
  `data_conversion/jobs/condor/reco_decoded_runs.sh`.
- `reconstruction/jobs/run_tracking_batch.py` writes into its input file: use `--outdir`.
- No data, outputs or large files in the repository or in an AFS home (limited quota). `work/` is git-ignored.
- If a hook, the sandbox or a permission blocks an action, do not look for a way around it: say what you wanted to do.

## Shared machines

- Login nodes (lxplus, NAF) are shared: no long or heavy processes on them. Use HTCondor.
- Do not submit jobs unless asked to. Write the script or the DAG, show the command, and test on a few events first.
- While the HTCondor jobs of a checkout run, do not rebuild, pull, change branch or edit the scripts they read in it.
- No recursive searches (`find`, `grep -R`, `du`, ...) over AFS, CVMFS or EOS beyond the directory needed.

## Code

- Key4hep only: `source init_siwecalsoft.sh` (release pinned in `.key4hep-release`). Do not mix environments in a shell.
- C++17/C++20 and Python 3, following the style of the surrounding code. Change only what was asked.
- No personal paths in the code, no second copy of a mapping or calibration table.
- Plots follow [docs/plot_style.md](docs/plot_style.md).
- Before calling something done: `./build.sh` (it builds and runs the tests). If the tests were not run, or fail, say so.
- Changes to the core (`reconstruction/`, `simulation/`, `data_conversion/`, `common/`) go in a branch and a pull request.

## Reporting

- Say what was checked and how, and keep apart what was measured, what was read in the code and what is a guess.
- Correct your own mistakes openly.
