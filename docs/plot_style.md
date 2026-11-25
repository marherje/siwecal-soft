# SiW-ECAL plot style

One colour and drawing convention for every data–simulation comparison of the SiW-ECAL test-beam analysis, so that
data, undigitised and digitised simulation read the same way in every report. It lives in two files, which are the
reference (this page only describes them):

- Python (matplotlib): `common/python/siwecal_common/plot_style.py`
- ROOT / PyROOT: `common/root/siwecal_style.C`

## Colours

| sample | colour | drawn as |
|---|---|---|
| Data | `#29a3dc` (blue, `DATA`) | points with error bars; horizontal bar = bin width |
| Sim, no digitisation | `#eda100` (orange, `NODIGI`) | dotted histogram |
| Sim, digitised | `#c0392b` (red, `DIGI`) | hatched histogram; the reference red |

Two productions of the same kind in one figure add one colour each, with a different marker:

| sample | colour | drawn as | marker | Python | ROOT |
|---|---|---|---|---|---|
| Data, reference production | `#29a3dc` (blue, `DATA`) | points with error bars | full circle | `data_points` | `Data` |
| Data, second production | `#2a4d9b` (indigo, `DATA2`) | points with error bars | open square | `data2_points` | `Data2` |
| Sim digitised, reference production | `#c0392b` (red, `DIGI`) | hatched histogram / dash-dot line | triangle | `sim_hist` / `sim_line` with `DIGI_STYLE` | `Digi` |
| Sim digitised, second production | `#cc4aa6` (magenta, `DIGI2`) | hatched histogram / dashed line | plus | `sim_hist` / `sim_line` with `DIGI2_STYLE` | `Digi2` |

- The reference is the production already in use (data as reconstructed, the current campaign); the second is the new one
  (corrected data, another campaign). The same sample keeps its colour in every figure of a study.
- Say in the legend what each one is ("Data, sag corrected"), not "data 1" and "data 2".
- For a ratio between two productions (data2 / data, sim2 / sim), draw it in the colour of the numerator against the grey
  line at 1; say in the axis title which over which.
- Keep the markers: the five colours pass the colour-blindness checks together, but not by much (worst pair `DATA` -
  `DIGI2`, Delta E 8.4). In a histogram with both simulations, the second is an outline (`fill=False`).
- With three or more digitised models use the reds below, not `DIGI2`.

Several digitised models in one figure (geometry variants, campaigns, digitiser settings) take a gradient of reds,
light to dark around the reference red, each with its own hatch, line style and marker, so they stay distinct in print
and for colour-blind readers. `reds(n)` returns the first n; model i always gets the same style, whatever n is (at
most 5 per figure).

| model | colour | hatch | line style | marker |
|---|---|---|---|---|
| 1 | `#f08c76` | `////` | solid | `o` |
| 2 | `#e0583c` | `\\\\` | dashed | `s` |
| 3 | `#c0392b` | `xxx` | dash-dot | `^` |
| 4 | `#8e2116` | `...` | dotted | `D` |
| 5 | `#5e1008` | `++` | dash-dot-dot | `v` |

Analytic curves (an estimate, a model formula) and shaded reference bands are neutral grey: blue is reserved for the
data.

## How to draw each kind of plot

| plot | data | simulation | function |
|---|---|---|---|
| Binned distribution: per layer, per radial bin, per time bin, a histogram | points with error bars, bin width as a horizontal bar | histograms: hatched for digitised, dotted for undigitised | `data_points`, `sim_hist`, `nodigi_hist` |
| Trend with several curves: against energy, k, charge Q, distance | points with error bars | lines, one style per model | `data_points`, `sim_line` |
| Ratio sim / data, difference sim − data | none: a grey reference line at 1 (or 0) | lines (or outline histograms), one style per model | `sim_line`, `sim_hist(fill=False)` |
| Two productions, data vs data or sim vs sim | `data_points` + `data2_points` | `DIGI_STYLE` + `DIGI2_STYLE` | `sim_hist`, `sim_line` |
| Width difference sim − data (R90, Molière radius) | none: grey line at 0 | lines, with the ±½ pad band | `pad_band` |

- **Half-pad band.** On a sim − data width axis, `pad_band` shades ±2.77 mm, half of the 5.53 mm pad. It is not an
  uncertainty: an R90 over thousands of events is known far better than a pad. It marks the detector granularity; a
  difference inside it is below one cell.
- **Several digitised models in one histogram.** Model i always takes red i, hatch i and line style i of the table
  above. Only the reference model keeps its hatch; the others are outlines, so the hatches do not mix. No hatch on a
  log axis.
- **Legends.** When a legend would sit on top of the histograms, put it in one row above the panels.
- **Axes.** `RC` sets light grids, no top or right spine, 9 pt text and frameless legends.
- **Normalisation.** Compared histograms are drawn with unit area over the shown range, unless the absolute count is
  the point of the plot.

## Python

```python
import matplotlib.pyplot as plt
from siwecal_common import plot_style as ps     # on PYTHONPATH after source init_siwecalsoft.sh

plt.rcParams.update(ps.RC)
fig, ax = plt.subplots()
ps.data_points(ax, x, y, yerr, edges)                          # data
ps.nodigi_hist(ax, nodigi, edges, label="Sim (no digitisation)")
ref, other = ps.reds(3)[2], ps.reds(3)[0]
ps.sim_hist(ax, digi, edges, ref, label="Sim (digitised)")      # reference model: hatched
ps.sim_hist(ax, digi_v2, edges, other, label="model 1", fill=False)   # others: outlines
```

Two productions (e.g. uncorrected data vs sim with sag, and corrected data vs sim without it):

```python
ps.data_points(ax, x, y, yerr, edges, label="Data, not corrected")
ps.data2_points(ax, x, y2, y2err, edges, label="Data, sag corrected")
ps.sim_hist(ax, sim, edges, ps.DIGI_STYLE, label="Sim with sag")
ps.sim_hist(ax, sim2, edges, ps.DIGI2_STYLE, label="Sim without sag", fill=False)
```

`edges_of(x)` gives bin edges around bin centres; `data_points` takes the matplotlib `errorbar` options (`fmt`,
`ms`, `capsize`, ...) for the rare case that needs them. Examples in the repo: `analysis/final_panels.py`,
`analysis/position_scans.py`, `analysis/contained_resolution.py`.

## ROOT

`TColor::GetColor("#rrggbb")` registers each colour once and returns its index, so the palette works in any ROOT
macro or PyROOT script without hard-coded colour numbers. `siwecal_style.C` defines the colours, the hatches and line
styles of the digitised models (ROOT styles 3004–3007 and 3013, the closest to the matplotlib hatches), one helper
per sample kind (`siwecal::SetStyle()`, `Data(h)`, `NoDigi(h)`, `Digi(h, i)` with i = 0 light .. 4 dark, 2 = the
reference red) and a basic example: data as points with error bars, the undigitised simulation as a dotted line, two
digitised models as hatched histograms.

    root -l -b -q common/root/siwecal_style.C          # the example -> siwecal_style_root.png

In PyROOT: `ROOT.gROOT.LoadMacro("common/root/siwecal_style.C")`, then `ROOT.siwecal.SetStyle()`,
`ROOT.siwecal.Data(h)`, `ROOT.siwecal.Data2(h)`, `ROOT.siwecal.Digi(h, 1)`, `ROOT.siwecal.Digi2(h)` and so on.

## Changing the style

Change `plot_style.py` and `siwecal_style.C` together (same colours, hatches and line styles, model by model), and
this page with them.
