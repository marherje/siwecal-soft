#!/usr/bin/env python
"""
Activity along 150 GeV muon tracks at normal incidence: knock-on electrons (delta rays), bremsstrahlung and pair
production along the track, in data and simulation; and the numbers behind "muon DIS cannot be measured here".

    python3 analysis/muon_deep_dive.py <outdir> [--max-events N]

Samples (valtrees): data e151 (th210) and 85 (th220) in Reconstruction/; simulation muon_v1 (digitised and undigitised,
same thresholds). Run 4 (th230) is left out: most of its events are showers, not muons.
Muon track: hits in >= 12 layers, among them the first 3 and the last 3, barycentre within 60 mm of the centre.
Per event: extra hits = nhit - layers hit; excess energy = sum_energy - layers hit x (median energy of a track hit);
layer with the largest energy. Writes <outdir>/muon_deep_dive.json and the plots (PNG); refuses an existing outdir.
"""
import argparse
import glob
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import uproot  # noqa: E402

from siwecal_common import paths, plot_style as ps  # noqa: E402

N_A = 6.022e23
W_THICK_MM = None   # read from the slab description
W_DENSITY = 19.24   # g/cm3, TungstenDens1924 of the geometry
Z_A_W = 74 / 183.84
K_BB = 0.307075     # MeV cm2 / mol, 4 pi N_A r_e^2 m_e c^2
MUON_E_GEV = 150.0
M_MU, M_E = 0.10566, 0.000511


def samples():
    reco, sim = paths.reconstruction_dir(), os.path.join(paths.simulation_dir(), "Processed", "muon_v1", "pid")
    out = {}
    for th, run in (("th210", "TB2026CERN_eudaq_run_000151"), ("th220", "TB2026CERN_run_000085")):
        out[th] = {"data": f"{reco}/{run}/ecal_{run}.valtree.root",
                   "digi": glob.glob(f"{sim}/{th}_mu150_*_digi/*.valtree.root")[0],
                   "nodigi": glob.glob(f"{sim}/{th}_mu150_*_nodigi/*.valtree.root")[0],
                   "run": run}
    return out


def load(path, nmax):
    t = uproot.open(path)["ecal"]
    a = t.arrays(["nhit_chan", "n_layers_hit", "sum_energy", "bar_x", "bar_y", "hits_per_layer", "energy_per_layer"],
                 library="np", entry_stop=nmax)
    hpl = np.stack([np.asarray(h, float) for h in a["hits_per_layer"]])
    epl = np.stack([np.asarray(e, float) for e in a["energy_per_layer"]])
    track = ((a["n_layers_hit"] >= 12) & (hpl[:, :3] > 0).all(1) & (hpl[:, -3:] > 0).all(1)
             & (np.abs(a["bar_x"]) < 60) & (np.abs(a["bar_y"]) < 60))
    clean = track & (a["nhit_chan"] == a["n_layers_hit"])
    per_hit = np.median(a["sum_energy"][clean] / a["n_layers_hit"][clean]) if clean.any() else np.nan
    k = track
    L = a["n_layers_hit"][k].astype(float)
    return {"entries": int(t.num_entries), "read": int(len(track)), "tracks": int(k.sum()),
            "mip_per_hit": float(per_hit),
            "extra": (a["nhit_chan"][k] - a["n_layers_hit"][k]).astype(float),
            "excess": a["sum_energy"][k] - L * per_hit,
            "emax": epl[k].max(1), "lmax": epl[k].argmax(1), "burst": (hpl[k] >= 5).sum(1)}


def frac(x, cut):
    n = (x > cut).sum()
    return float(n / len(x)), float(np.sqrt(max(n, 1)) / len(x))


def tail_slope(x, lo, hi):
    """Power-law index of the tail dN/dx ~ x^-s between lo and hi (maximum likelihood, truncated)."""
    v = x[(x > lo) & (x < hi)]
    if len(v) < 30:
        return np.nan, np.nan, len(v)
    grid = np.linspace(1.05, 4.0, 600)
    ll = [len(v) * np.log((s - 1) / (lo ** (1 - s) - hi ** (1 - s))) - s * np.log(v).sum() for s in grid]
    i = int(np.argmax(ll))
    curv = (ll[i + 1] - 2 * ll[i] + ll[i - 1]) / (grid[1] - grid[0]) ** 2 if 0 < i < len(grid) - 1 else np.nan
    return float(grid[i]), float(1 / np.sqrt(-curv)) if curv < 0 else np.nan, int(len(v))


def delta_rays_above(t_min_mev, x_gcm2):
    """Knock-on electrons with kinetic energy > t_min per muon (Bhabha-like 1/T^2 spectrum, spin terms neglected)."""
    g = MUON_E_GEV / M_MU
    t_max = 2 * M_E * (g * g - 1) / (1 + 2 * g * M_E / M_MU + (M_E / M_MU) ** 2) * 1e3   # MeV
    return 0.5 * K_BB * Z_A_W * x_gcm2 * (1 / t_min_mev - 1 / t_max), t_max


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--max-events", type=int, default=600000, help="per sample")
    a = ap.parse_args()
    if os.path.exists(a.outdir):
        raise SystemExit(f"{a.outdir} exists")
    os.makedirs(a.outdir)
    plt.rcParams.update(ps.RC)
    from siwecal_common.slab_description import load_slab_description
    w_mm = sum(load_slab_description(paths.mapping_file("slab_z_positions.yml")).w_thickness_mm)
    x_w = w_mm / 10 * W_DENSITY                      # g/cm2 crossed at normal incidence
    res = {"w_mm": w_mm, "x_w_gcm2": x_w, "x0_w": w_mm / 3.504, "samples": {}}

    S = {th: {k: load(p, a.max_events) for k, p in d.items() if k != "run"} for th, d in samples().items()}
    style = {"data": dict(color=ps.DATA), "digi": ps.DIGI_STYLE, "nodigi": dict(color=ps.NODIGI)}
    label = {"data": "Data", "digi": "Sim (digitised)", "nodigi": "Sim (no digitisation)"}
    cuts_hits, cuts_e = (5, 10, 30, 60, 100), (10, 20, 50, 100, 200, 500)
    for th, d in S.items():
        r = res["samples"][th] = {}
        for k, s in d.items():
            r[k] = {"entries": s["entries"], "read": s["read"], "tracks": s["tracks"], "mip_per_hit": s["mip_per_hit"],
                    "extra_hits": {c: frac(s["extra"], c) for c in cuts_hits},
                    "excess_mip": {c: frac(s["excess"], c) for c in cuts_e},
                    "layer_over_100mip": frac(s["emax"], 100),
                    "tail_slope_20_500": tail_slope(s["excess"], 20, 500)}

        # 1) extra hits and 2) excess energy: distributions (unit area) and ratio sim / data
        for var, xlabel, edges, name in (("extra", "Hits beyond one per layer", np.arange(-0.5, 150.5, 3), "extra_hits"),
                                         ("excess", "Excess energy along the track [MIP]",
                                          np.logspace(np.log10(5), np.log10(3000), 36), "excess_energy")):
            fig, (ax, axr) = plt.subplots(2, 1, figsize=(7, 6), sharex=True, gridspec_kw={"height_ratios": [2.4, 1]})
            h = {}
            for k in ("data", "nodigi", "digi"):
                c, _ = np.histogram(d[k][var], edges)
                n = len(d[k][var])
                h[k] = (c / n, np.sqrt(c) / n)
            x = 0.5 * (edges[1:] + edges[:-1]) if var == "extra" else np.sqrt(edges[1:] * edges[:-1])
            ps.nodigi_hist(ax, h["nodigi"][0], edges, label=label["nodigi"])
            ps.sim_hist(ax, h["digi"][0], edges, ps.DIGI_STYLE, label=label["digi"], fill=False)
            ps.data_points(ax, x, h["data"][0], h["data"][1], edges, label=label["data"])
            ax.set_yscale("log")
            ax.set_ylabel("Fraction of muon tracks per bin")
            if var == "excess":
                ax.set_xscale("log")
            ok = h["data"][0] > 0
            for k in ("digi", "nodigi"):
                ps.sim_line(axr, x[ok], h[k][0][ok] / h["data"][0][ok],
                            ps.DIGI_STYLE if k == "digi" else {"color": ps.NODIGI, "ls": ":", "marker": "o"}, markers=False)
            axr.axhline(1, color="0.5", lw=1)
            axr.set_ylim(0, 2.5)
            axr.set_ylabel("sim / data")
            axr.set_xlabel(xlabel)
            ax.legend(loc="upper right")
            ax.set_title(f"150 GeV muons, {th}: {d['data']['tracks']} data / {d['digi']['tracks']} sim tracks", fontsize=9)
            fig.tight_layout()
            fig.savefig(f"{a.outdir}/{name}_{th}.png", dpi=130)
            plt.close(fig)

        # 3) where along the stack the largest deposit sits, for events with excess > 50 MIP
        fig, ax = plt.subplots(figsize=(7, 3.6))
        edges = np.arange(-0.5, 15.5, 1)
        for k in ("data", "nodigi", "digi"):
            m = d[k]["excess"] > 50
            c, _ = np.histogram(d[k]["lmax"][m], edges)
            f = c / max(c.sum(), 1)
            if k == "data":
                ps.data_points(ax, np.arange(15), f, np.sqrt(c) / max(c.sum(), 1), edges, label=label[k])
            elif k == "digi":
                ps.sim_hist(ax, f, edges, ps.DIGI_STYLE, label=label[k], fill=False)
            else:
                ps.nodigi_hist(ax, f, edges, label=label[k])
        ax.set_xlabel("Layer with the largest deposit (excess > 50 MIP)")
        ax.set_ylabel("Fraction")
        ax.legend(loc="upper left", ncol=3, fontsize=7)
        fig.tight_layout()
        fig.savefig(f"{a.outdir}/depth_{th}.png", dpi=130)
        plt.close(fig)

    # expectations: delta rays and the muon-nucleus (photonuclear) rate
    gev_mip = 68.0    # sum_energy [MIP] per GeV of an EM shower at th210 (20 GeV positrons: ~1370 MIP)
    exp = {}
    for mip in (20, 50, 100, 200):
        n, t_max = delta_rays_above(mip / gev_mip * 1e3, x_w)
        exp[mip] = n
    res["delta_expected"] = {"gev_per_mip": 1 / gev_mip, "t_max_gev": t_max / 1e3, "n_above_excess_mip": exp}
    b_nucl = 0.4e-6        # g^-1 cm^2, photonuclear energy-loss coefficient of a 100-200 GeV muon (order of magnitude)
    c_nucl = b_nucl / N_A  # cm2: d(sigma)/dv ~ c / v per nucleon, v = nu / E
    dis = {}
    for nu_min in (1.0, 5.0, 20.0):
        sigma = c_nucl * np.log(MUON_E_GEV / nu_min)
        dis[nu_min] = {"sigma_ub": sigma * 1e30, "p_per_muon": sigma * x_w * N_A}
    res["nuclear"] = {"b_nucl": b_nucl, "by_nu_min_gev": dis}
    q2, e1 = 1.0, 75.0
    res["dis_kinematics"] = {"theta_mrad_q2_1": 1e3 * np.sqrt(q2 / (MUON_E_GEV * e1)),
                             "track_angle_resolution_mrad": 1e3 * (5.53 / np.sqrt(12)) * np.sqrt(12 / 15) / 225.0,
                             "multiple_scattering_mrad": 1e3 * 13.6e-3 / e1 * np.sqrt(w_mm / 3.504) *
                             (1 + 0.038 * np.log(w_mm / 3.504))}
    json.dump(res, open(f"{a.outdir}/muon_deep_dive.json", "w"), indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
