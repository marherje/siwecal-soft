/*
 * BeamSpot.h: the beam spot of one run as seen by the ECAL, and the tuning of the simulation gun that reproduces it
 * (run-by-run simulation: simulation/campaign/make_run_sim_dag.py, executable siwecal_beamspot).
 *
 *   measure     shower-like events (nhit > 0.5 * p90 of nhit over the file, as analysis/beam_spread.py), finite
 *               barycentres only: centre = median (bar_x, bar_y), width = IQR / 1.349, n = selected events
 *   initialGun  gun of the dummy pass: the data centre and width (floor 1 mm)
 *   tune        x_gun = x_dummy_gun + (x_data - x_dummy);  s_gun^2 = s_dummy_gun^2 + w_data^2 - w_dummy^2 (floor 1 mm)
 *   productionEvents  data statistics rounded up to whole chunks (at least one)
 *   closure     production vs data: centre shift and relative width; flagged beyond 1 mm or 5 %
 */
#ifndef SIWECAL_BEAMSPOT_H
#define SIWECAL_BEAMSPOT_H

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace siwecal::beamspot {

struct Spot { double x, y, wx, wy; long n; };
struct Gun { double x, y, sx, sy; };
struct Closure { double dx, dy, rwx, rwy; bool flag; };

/// q-th percentile (0-100) with linear interpolation between order statistics (numpy's default); NaN if empty.
inline double percentile(std::vector<double> v, double q) {
  if (v.empty()) return std::numeric_limits<double>::quiet_NaN();
  std::sort(v.begin(), v.end());
  const double pos = q / 100.0 * static_cast<double>(v.size() - 1);
  const auto lo = static_cast<std::size_t>(std::floor(pos));
  const std::size_t hi = std::min(lo + 1, v.size() - 1);
  return v[lo] + (pos - static_cast<double>(lo)) * (v[hi] - v[lo]);
}

inline Spot measure(const std::vector<int>& nhit, const std::vector<double>& barX, const std::vector<double>& barY) {
  const double nan = std::numeric_limits<double>::quiet_NaN();
  const double cut = 0.5 * percentile(std::vector<double>(nhit.begin(), nhit.end()), 90);
  std::vector<double> xs, ys;
  for (std::size_t i = 0; i < nhit.size() && i < barX.size() && i < barY.size(); ++i)
    if (nhit[i] > cut && std::isfinite(barX[i]) && std::isfinite(barY[i])) {
      xs.push_back(barX[i]);
      ys.push_back(barY[i]);
    }
  if (xs.empty()) return {nan, nan, nan, nan, 0};
  auto width = [](const std::vector<double>& v) { return (percentile(v, 75) - percentile(v, 25)) / 1.349; };
  return {percentile(xs, 50), percentile(ys, 50), width(xs), width(ys), static_cast<long>(xs.size())};
}

inline Gun initialGun(const Spot& data, double floorMm = 1.0) {
  return {data.x, data.y, std::max(data.wx, floorMm), std::max(data.wy, floorMm)};
}

inline Gun tune(const Spot& data, const Spot& dummy, const Gun& dummyGun, double floorMm = 1.0) {
  auto sigma = [floorMm](double s, double wData, double wDummy) {
    const double s2 = s * s + wData * wData - wDummy * wDummy;
    return s2 > floorMm * floorMm ? std::sqrt(s2) : floorMm;
  };
  return {dummyGun.x + (data.x - dummy.x), dummyGun.y + (data.y - dummy.y), sigma(dummyGun.sx, data.wx, dummy.wx),
          sigma(dummyGun.sy, data.wy, dummy.wy)};
}

inline long productionEvents(long nShowerlike, long chunk = 2000) {
  const long chunks = std::max(1L, (nShowerlike + chunk - 1) / chunk);
  return chunks * chunk;
}

inline Closure closure(const Spot& data, const Spot& sim, double maxShiftMm = 1.0, double maxRelWidth = 0.05) {
  Closure c{sim.x - data.x, sim.y - data.y, sim.wx / data.wx - 1.0, sim.wy / data.wy - 1.0, false};
  c.flag = !(std::fabs(c.dx) <= maxShiftMm && std::fabs(c.dy) <= maxShiftMm && std::fabs(c.rwx) <= maxRelWidth &&
             std::fabs(c.rwy) <= maxRelWidth);   // NaN counts as flagged
  return c;
}

}  // namespace siwecal::beamspot

#endif
