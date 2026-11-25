/*
 * siwecal_beamspot: beam spot of a valtree and gun tuning of the run-by-run simulation (siwecal/BeamSpot.h).
 *
 *   siwecal_beamspot measure <valtree.root> <out.json> [--tree ecal]
 *       {"x","y","wx","wy","n"} of the shower-like events (NaN written as null), "entries" = all events
 *   siwecal_beamspot tune <params.data.json> <dummy_spot.json> <out_params.json>
 *       the data params ("data" spot, "gun0" = gun of the dummy, optional "turn_deg" of the ECAL) plus "dummy" and the
 *       tuned "gun"
 *   siwecal_beamspot closure <params.json> <sim_spot.json> <out.json>
 *       {"data","sim","dx","dy","rwx","rwy","flag"}
 * Used by simulation/campaign/make_run_sim_dag.py and the run_sim_*.sh node scripts.
 */
#include "siwecal/BeamSpot.h"

#include "TFile.h"
#include "TTree.h"

#include <nlohmann/json.hpp>

#include <cmath>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using nlohmann::json;
namespace bs = siwecal::beamspot;

namespace {

json num(double v) { return std::isfinite(v) ? json(v) : json(nullptr); }
double val(const json& j, const char* k) { return j.at(k).is_null() ? std::nan("") : j.at(k).get<double>(); }

json toJson(const bs::Spot& s) { return {{"x", num(s.x)}, {"y", num(s.y)}, {"wx", num(s.wx)}, {"wy", num(s.wy)}, {"n", s.n}}; }
bs::Spot spot(const json& j) { return {val(j, "x"), val(j, "y"), val(j, "wx"), val(j, "wy"), j.at("n").get<long>()}; }
json toJson(const bs::Gun& g) { return {{"x", num(g.x)}, {"y", num(g.y)}, {"sx", num(g.sx)}, {"sy", num(g.sy)}}; }
bs::Gun gun(const json& j) { return {val(j, "x"), val(j, "y"), val(j, "sx"), val(j, "sy")}; }

json load(const std::string& path) {
  std::ifstream in(path);
  if (!in) throw std::runtime_error("cannot read " + path);
  return json::parse(in);
}

void save(const json& j, const std::string& path) {
  std::ofstream out(path);
  if (!out) throw std::runtime_error("cannot write " + path);
  out << j.dump(2) << "\n";
  if (!out) throw std::runtime_error("cannot write " + path);
}

bs::Spot measureFile(const std::string& path, const std::string& treeName, long& entries) {
  std::unique_ptr<TFile> f(TFile::Open(path.c_str(), "READ"));
  if (!f || f->IsZombie()) throw std::runtime_error("cannot open " + path);
  auto* t = f->Get<TTree>(treeName.c_str());
  if (!t) throw std::runtime_error("no tree '" + treeName + "' in " + path);
  int nhit = 0;
  double bx = 0, by = 0;
  t->SetBranchStatus("*", false);
  for (const char* b : {"nhit_chan", "bar_x", "bar_y"}) {
    if (!t->GetBranch(b)) throw std::runtime_error(std::string("no branch ") + b + " in " + path);
    t->SetBranchStatus(b, true);
  }
  t->SetBranchAddress("nhit_chan", &nhit);
  t->SetBranchAddress("bar_x", &bx);
  t->SetBranchAddress("bar_y", &by);
  const Long64_t n = t->GetEntries();
  entries = static_cast<long>(n);
  std::vector<int> nh(n);
  std::vector<double> xs(n), ys(n);
  for (Long64_t i = 0; i < n; ++i) {
    t->GetEntry(i);
    nh[i] = nhit;
    xs[i] = bx;
    ys[i] = by;
  }
  return bs::measure(nh, xs, ys);
}

int usage() {
  std::cerr << "usage: siwecal_beamspot measure <valtree.root> <out.json> [--tree ecal]\n"
               "       siwecal_beamspot tune <params.data.json> <dummy_spot.json> <out_params.json>\n"
               "       siwecal_beamspot closure <params.json> <sim_spot.json> <out.json>\n";
  return 2;
}

}  // namespace

int main(int argc, char** argv) {
  const std::vector<std::string> a(argv + 1, argv + argc);
  if (a.size() < 3) return usage();
  try {
    if (a[0] == "measure") {
      const std::string tree = (a.size() >= 5 && a[3] == "--tree") ? a[4] : "ecal";
      long entries = 0;
      json j = toJson(measureFile(a[1], tree, entries));
      j["entries"] = entries;   // every event of the tree, selected or not
      save(j, a[2]);
    } else if (a[0] == "tune" && a.size() == 4) {
      json p = load(a[1]);
      const bs::Spot dummy = spot(load(a[2]));
      p["dummy"] = toJson(dummy);
      p["gun"] = toJson(bs::tune(spot(p.at("data")), dummy, gun(p.at("gun0")), 1.0, p.value("turn_deg", 0.0)));
      save(p, a[3]);
    } else if (a[0] == "closure" && a.size() == 4) {
      const json p = load(a[1]);
      const bs::Spot data = spot(p.at("data")), sim = spot(load(a[2]));
      const bs::Closure c = bs::closure(data, sim);
      save({{"data", toJson(data)}, {"sim", toJson(sim)}, {"dx", num(c.dx)}, {"dy", num(c.dy)},
            {"rwx", num(c.rwx)}, {"rwy", num(c.rwy)}, {"flag", c.flag}},
           a[3]);
    } else {
      return usage();
    }
  } catch (const std::exception& e) {
    std::cerr << "siwecal_beamspot: " << e.what() << "\n";
    return 1;
  }
  return 0;
}
