/*
 * EcalEventSelection: the event selection of the PID stage, as one configurable filter. An event it rejects is
 * never handed to the IOSvc writer (nor to EcalValTreeWriter, which asks this filter), so the EDM4hep and the
 * valtree of a job hold exactly the selected events and the job's options are the full record of the selection.
 *
 *   RequireHits  (default true)  at least one hit and a positive total energy: the events without any signal,
 *                                the rule every PID output applied (siwecal_validation's EventData loader);
 *   Cuts         ["name:min:max", ...] inclusive bounds on the per-event scalars of EcalShowerVars.h
 *                (scalarNames(): nhit, energy, mip_likeness, weighte, moliere, transverse_rms, bar_r,
 *                barxy_min_border_distance, shower_start, ..., e_over_nhit); an empty bound is open
 *                ("moliere:45:" = moliere >= 45). AND of all of them. A NaN value fails every bound.
 *   IsShower     -1 any (default), 1 only showers, 0 only non-showers.
 *
 * The driver (reconstruction/jobs/run_pid_batch.py) turns siwecal_validation's CutSet (CLI and the per-energy cuts
 * of the run-list YAML) into these properties. Replaces EcalEventCut (one variable per instance) and the Python
 * filtering that ran after the job (EventData + edm4hep_pid.write_filtered).
 */
#include "siwecal/EcalShowerVars.h"

#include "Gaudi/Property.h"
#include "k4FWCore/FilterPredicate.h"

#include "edm4hep/CalorimeterHitCollection.h"
#include "edm4hep/ClusterCollection.h"

#include <atomic>
#include <cmath>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

struct EcalEventSelection final
    : k4FWCore::FilterPredicate<bool(const edm4hep::ClusterCollection&, const edm4hep::CalorimeterHitCollection&)> {
  EcalEventSelection(const std::string& name, ISvcLocator* svcLoc)
      : FilterPredicate(name, svcLoc, {KeyValue("InputClusters", "ECalPid"), KeyValue("InputCaloHits", "ECalHits")}) {}

  struct Cut { std::string name; std::size_t index; double lo, hi; };

  StatusCode initialize() override {
    StatusCode sc = FilterPredicate::initialize();
    if (sc.isFailure()) return sc;
    const auto& names = k4siwecal::scalarNames();
    auto indexOf = [&](const std::string& n) -> long {
      for (std::size_t i = 0; i < names.size(); ++i) if (names[i] == n) return static_cast<long>(i);
      return -1;
    };
    m_energyIndex = static_cast<std::size_t>(indexOf("energy"));
    m_showerIndex = static_cast<std::size_t>(indexOf("is_shower"));
    for (const auto& spec : m_cutSpecs.value()) {
      std::vector<std::string> f;
      std::stringstream ss(spec);
      for (std::string t; std::getline(ss, t, ':');) f.push_back(t);
      while (f.size() < 3) f.emplace_back();
      const long idx = indexOf(f[0]);
      if (idx < 0 || f.size() != 3) {
        error() << "cut '" << spec << "': expected 'name:min:max' with name one of EcalShowerVars scalarNames()"
                << endmsg;
        return StatusCode::FAILURE;
      }
      const double inf = std::numeric_limits<double>::infinity();
      m_cuts.push_back({f[0], static_cast<std::size_t>(idx), f[1].empty() ? -inf : std::stod(f[1]),
                        f[2].empty() ? inf : std::stod(f[2])});
    }
    info() << "selection: " << (m_requireHits.value() ? "hits and energy > 0" : "no hit requirement");
    for (const auto& c : m_cuts) info() << ", " << c.name << " in [" << c.lo << ", " << c.hi << "]";
    if (m_isShower.value() >= 0) info() << ", is_shower == " << m_isShower.value();
    info() << endmsg;
    return StatusCode::SUCCESS;
  }

  bool operator()(const edm4hep::ClusterCollection& clusters, const edm4hep::CalorimeterHitCollection& hits) const override {
    ++m_nSeen;
    if (clusters.size() < 1) return false;
    const auto par = clusters[0].getShapeParameters();
    auto value = [&](std::size_t i) { return i < par.size() ? static_cast<double>(par[i]) : std::nan(""); };
    if (m_requireHits.value() && (hits.size() == 0 || !(value(m_energyIndex) > 0))) return false;
    for (const auto& c : m_cuts) {
      const double v = value(c.index);
      if (!(v >= c.lo && v <= c.hi)) return false;   // NaN fails
    }
    if (m_isShower.value() >= 0 && (value(m_showerIndex) != 0) != (m_isShower.value() == 1)) return false;
    ++m_nPassed;
    return true;
  }

  StatusCode finalize() override {
    info() << m_nPassed.load() << " / " << m_nSeen.load() << " events selected" << endmsg;
    return FilterPredicate::finalize();
  }

private:
  Gaudi::Property<bool> m_requireHits{this, "RequireHits", true,
                                      "Drop events without hits or with non-positive total energy"};
  Gaudi::Property<std::vector<std::string>> m_cutSpecs{this, "Cuts", {},
                                                       "'name:min:max' bounds on EcalShowerVars scalars, inclusive"};
  Gaudi::Property<int> m_isShower{this, "IsShower", -1, "-1 any, 1 showers only, 0 non-showers only"};
  std::vector<Cut> m_cuts;
  std::size_t m_energyIndex = 0, m_showerIndex = 0;
  mutable std::atomic<long long> m_nSeen{0}, m_nPassed{0};
};

DECLARE_COMPONENT(EcalEventSelection)
