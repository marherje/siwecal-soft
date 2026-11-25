// BeamSpot.h: shower-like selection, beam centre and width, gun tuning, statistics and closure of the run-by-run
// simulation (simulation/campaign/make_run_sim_dag.py), on synthetic data.
#include "siwecal/BeamSpot.h"

#include <cmath>
#include <iostream>
#include <random>
#include <vector>

static int fails = 0;
#define CHECK(c) do { if (!(c)) { std::cerr << "FAIL line " << __LINE__ << ": " #c "\n"; ++fails; } } while (0)

using namespace siwecal::beamspot;

int main() {
  CHECK(std::fabs(percentile({1, 2, 3, 4}, 50) - 2.5) < 1e-12);
  CHECK(std::isnan(percentile({}, 50)));

  {  // Gaussian beam: median and IQR/1.349 recover the centre and sigma
    std::mt19937 rng(1);
    std::normal_distribution<double> gx(5, 10), gy(-3, 4);
    std::vector<int> nhit(20000, 100);
    std::vector<double> x(20000), y(20000);
    for (std::size_t i = 0; i < x.size(); ++i) { x[i] = gx(rng); y[i] = gy(rng); }
    const Spot s = measure(nhit, x, y);
    CHECK(s.n == 20000);
    CHECK(std::fabs(s.x - 5) < 0.3 && std::fabs(s.y + 3) < 0.15);
    CHECK(std::fabs(s.wx - 10) < 0.3 && std::fabs(s.wy - 4) < 0.15);
  }
  {  // shower-like: nhit > 0.5 * p90
    std::vector<int> nhit(500, 1);
    nhit.insert(nhit.end(), 500, 100);
    std::vector<double> x(1000, 1.0), y(1000, 2.0);
    CHECK(measure(nhit, x, y).n == 500);
  }
  {  // NaN barycentres are left out
    std::vector<int> nhit(1000, 100);
    std::vector<double> x(1000, 3.0), y(1000, 4.0);
    for (std::size_t i = 0; i < 1000; i += 2) x[i] = std::nan("");
    const Spot s = measure(nhit, x, y);
    CHECK(s.n == 500 && s.x == 3.0 && s.y == 4.0);
  }
  {  // no events at all
    const Spot s = measure({}, {}, {});
    CHECK(s.n == 0 && std::isnan(s.x) && std::isnan(s.wx));
  }
  {  // tuning: shift by the centre difference, quadrature on the width
    const Spot data{10, 0, 12, 12, 1000}, dummy{8, 0, 13, 13, 1000};
    const Gun g = tune(data, dummy, Gun{10, 0, 12, 12});
    CHECK(std::fabs(g.x - 12) < 1e-12 && std::fabs(g.sx - std::sqrt(119.0)) < 1e-12);
  }
  {  // ECAL turned by 60 deg: the lab shift and the quadrature in x are cos(60) and cos^2(60) of the local ones
    const Gun g = tune(Spot{10, 3, 12, 12, 1000}, Spot{8, 1, 13, 13, 1000}, Gun{10, 0, 12, 12}, 1.0, 60.0);
    CHECK(std::fabs(g.x - 11) < 1e-12 && std::fabs(g.y - 2) < 1e-12);
    CHECK(std::fabs(g.sx - std::sqrt(144 - 25 * 0.25)) < 1e-12 && std::fabs(g.sy - std::sqrt(119.0)) < 1e-12);
  }
  {  // a dummy wider than the data floors the gun sigma at 1 mm
    const Gun g = tune(Spot{0, 0, 2, 2, 100}, Spot{0, 0, 20, 20, 100}, Gun{0, 0, 3, 3});
    CHECK(g.sx == 1.0 && g.sy == 1.0);
  }
  {  // initial gun = data centre and width, floored
    const Gun g = initialGun(Spot{4, -2, 0.5, 9, 10});
    CHECK(g.x == 4 && g.y == -2 && g.sx == 1.0 && g.sy == 9);
  }
  CHECK(productionEvents(1) == 2000 && productionEvents(2000) == 2000 && productionEvents(2001) == 4000 &&
        productionEvents(0) == 2000);
  {  // closure flags
    const Spot data{0, 0, 10, 10, 1000};
    CHECK(!closure(data, Spot{0.5, 0, 10.2, 10, 1000}).flag);
    CHECK(closure(data, Spot{1.5, 0, 10, 10, 1000}).flag);
    const Closure c = closure(data, Spot{0, 0, 9.4, 10, 1000});
    CHECK(c.flag && std::fabs(c.rwx + 0.06) < 1e-12);
  }
  std::cout << (fails ? "FAILED" : "OK") << "\n";
  return fails ? 1 : 0;
}
