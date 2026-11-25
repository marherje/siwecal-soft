# Pion samples

The equivalent of the test-beam pion runs, to validate the pion simulation, and the pion background at E2. Nothing
produced yet. Setup: [running_campaigns.md](running_campaigns.md). Everything goes through
`simulation/campaign/launch_pions.sh` (modes, options and environment in its header); without `--submit` it only writes
the DAGs (`reco` also creates the empty run folders).

## 1. Equivalent of the data (10, 20, 30 GeV, th210)

`simulation/campaign/runs_pion.txt`: runs 161, 162 (10 GeV), 164 (20), 165 (30), decoded but not reconstructed.

    bash simulation/campaign/launch_pions.sh reco --submit     # event building + PID
    bash simulation/campaign/launch_pions.sh valtree           # when it has finished
    bash simulation/campaign/launch_pions.sh runs              # check the printout: 4 runs; then with --submit

From another account: `DATA_RECO=<your EOS folder>` in the three commands and `--out <your EOS folder>` in `runs`.

`reco` marks the CONVERT nodes of `generate_reco_dag.py` DONE: each of these runs is decoded in one
`chunk_0000.root`, but the generator lists every raw `.bin_NNNN` file and CONVERT would write chunk_0001... into the
shared `rundata_converted_gaudi/`. Do not call the generator directly on these runs.

The gun is tuned per run on the data spot, and the number of events follows the shower-like data events (10 GeV: two
files). That cut (nhit > 0.5 x p90) was made for electrons: with MIP-like pions, or electrons in the beam, look at
`closure.tsv` before using the samples.

    python3 analysis/run_shapes.py <.../Processed/pion_data_v1> --runs simulation/campaign/runs_pion.txt

(`FINAL_RECO=<DATA_RECO>` if it is not Reconstruction.) It compares shower-like events only; the inclusive
distributions need their own plots.

## 2. Background at E2 (10, 20, 30, 40, 50 GeV, th230)

`simulation/campaign/pion_points.txt`, one file per energy, 50k events each; independent of step 1, to be redone if the
comparison asks for a change of the simulation:

    bash simulation/campaign/launch_pions.sh e2                # check the printout; then with --submit

Output: `pid/<name>_{digi,nodigi}/*.valtree.root` (hits and shower variables) and `trees/ecal_<name>{,_simple}.root`.
More statistics: a new campaign and seed offset (the same offset repeats the events), e.g.

    E2_CAMPAIGN=pion_E2_big E2_SEED=90000000 NEVENTS=500000 bash simulation/campaign/launch_pions.sh e2 --out <your EOS folder>

Seeds are offset + 1000 x point + chunk: keep to at most 1000 chunks (2M events) per energy, or they repeat between
points.

## 3. More electrons at E2 (52, 74, 99 GeV, th230)

final_v11 has the statistics of the data runs (digitised, shower-like): 147 895 events at 52 GeV (run 28) and 45 987 at
74 GeV (run 29); there is no 99 GeV run at E2. `simulation/campaign/electron_points_E2.txt` has the tuned guns of the
first two and an assumed one at 99 GeV:

    python3 simulation/campaign/make_sim_dag.py --campaign electron_E2_v1 --nevents 200000 --seed-offset 100000000 \
        --points simulation/campaign/electron_points_E2.txt --out <your EOS folder>   # then with --submit

Tests: `pytest tests/control/test_pion_samples.py`.
