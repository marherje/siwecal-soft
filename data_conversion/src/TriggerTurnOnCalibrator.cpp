// TriggerTurnOnCalibrator -- the trigger turn-on of a threshold set as the digitiser uses it
// (common/mappings/digi_calibration.yml: threshold_mip / sigma_mip / efficiency / threshold_adc of the set, and every
// slab's own threshold_adc / sigma_adc / efficiency in slab_overrides). Gaudi port of analysis/trigger_turnon.py with
// analysis/compare_shapers.data_turnon (retired), same selection, binning and fits.
//
// It differs from PedestalMipCalibrator Mode=FitTrigger on purpose (the per-chip / per-channel tables of
// calib_dir()/MuonCalib/trigger/): that one uses every readout of the muon calibration runs; this one takes, per
// acquisition, slab, chip and channel, the SCA with the largest pedestal-subtracted amplitude of a beam run, the
// definition the simulation's set and slab turn-ons were measured and tuned with (final_v9).
//
// Mode=Fill  InputFiles = decoded chunks of one run, the first AcquisitionsPerChunk entries of each. Per acquisition,
//   slab, chip (array position) and channel: amplitude = adc_high - pedestal (PedestalFile, the set's high-gain
//   table, per SCA); an SCA counts if adc_high > 0, the amplitude is finite, hitbit_high >= 0 and badbcid == 0; the
//   one with the largest amplitude is taken, with its hit bit, and kept if the channel has an MPV in the set's MIP
//   table (MipFile, 0 < MPV <= 100 ADC). Its amplitude fills the turn-on histograms (fired / all): in ADC, 0-160 by 2,
//   for all slabs and per slab; in MIP (amplitude / MPV), 0-5 by 0.1. -> OutputFile (text).
// Mode=Fit   FillFiles (summed) -> OutputFile: the set's turn-on in MIP and in ADC (chi2 fit of the bins with >= 30
//   entries, binomial errors floored at 1e-4) and every slab's in ADC (binomial maximum likelihood over all bins with
//   entries, slabs with >= 2000 entries), P(x) = plateau * 0.5 * (1 + erf((x - mu) / (sqrt(2) sigma))).
//   tools: data_conversion/jobs/calibration/run_trigger_turnon.py (driver, writes the YAML block).
#include "Gaudi/Algorithm.h"
#include "Gaudi/Property.h"
#include "GaudiKernel/MsgStream.h"

#include "siwecal/DataPath.h"
#include "siwecal/SlbFrameDecoder.h"  // kSlbDepth, kSkirocsPerAsu, kScasInSkiroc, kChannelsInSkiroc

#include "Math/Functor.h"
#include "Math/Factory.h"
#include "Math/Minimizer.h"
#include "TFile.h"
#include "TTree.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <map>
#include <limits>
#include <memory>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>

namespace {
using k4siwecal::kChannelsInSkiroc;
using k4siwecal::kScasInSkiroc;
using k4siwecal::kSkirocsPerAsu;
using k4siwecal::kSlbDepth;
constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
constexpr int kNAdc = 80;    // 0 .. 160 ADC by 2
constexpr int kNMip = 50;    // 0 .. 5 MIP by 0.1

struct Fit { double mu = kNaN, sigma = kNaN, plateau = kNaN; bool ok() const { return std::isfinite(mu) && std::isfinite(sigma) && std::isfinite(plateau); } };

double model(double x, double mu, double sg, double pl) { return pl * 0.5 * (1.0 + std::erf((x - mu) / (std::sqrt(2.0) * sg))); }

// numpy.percentile(..., linear)
double percentile(std::vector<double> v, double q) {
  std::sort(v.begin(), v.end());
  const double pos = q / 100.0 * (v.size() - 1);
  const std::size_t lo = static_cast<std::size_t>(std::floor(pos));
  const std::size_t hi = std::min(lo + 1, v.size() - 1);
  return v[lo] + (pos - lo) * (v[hi] - v[lo]);
}

// minimise f over 3 bounded parameters (Minuit2 Migrad, then Simplex if it did not converge); returns (par, fval)
std::pair<std::vector<double>, double> minimise(const std::function<double(const double*)>& f, const double* start,
                                                const double* lo, const double* hi) {
  std::unique_ptr<ROOT::Math::Minimizer> m(ROOT::Math::Factory::CreateMinimizer("Minuit2", "Migrad"));
  m->SetMaxFunctionCalls(200000);
  m->SetTolerance(1e-8);
  m->SetPrintLevel(-1);
  ROOT::Math::Functor fn(f, 3);
  m->SetFunction(fn);
  const char* names[3] = {"mu", "sigma", "plateau"};
  for (int i = 0; i < 3; ++i) {
    const double step = std::max(1e-3, 0.05 * std::fabs(start[i]));
    if (std::isfinite(hi[i])) m->SetLimitedVariable(i, names[i], start[i], step, lo[i], hi[i]);
    else m->SetLowerLimitedVariable(i, names[i], start[i], step, lo[i]);
  }
  m->Minimize();
  const double* x = m->X();
  return {{x[0], x[1], x[2]}, m->MinValue()};
}

// trigger_turnon.fit_turn_on: chi2 over the bins with >= minEntries entries
Fit chi2Fit(const std::vector<double>& c, const std::vector<double>& num, const std::vector<double>& den,
            double minEntries = 30) {
  std::vector<double> x, e, w;
  for (std::size_t i = 0; i < c.size(); ++i)
    if (den[i] >= minEntries) {
      const double eff = num[i] / den[i];
      x.push_back(c[i]);
      e.push_back(eff);
      w.push_back(std::sqrt(std::max(eff * (1 - eff), 1e-4) / den[i]));
    }
  if (x.size() < 6) return {};
  const double p70 = percentile(x, 70);
  double s = 0;
  int n = 0;
  for (std::size_t i = 0; i < x.size(); ++i) if (x[i] > p70) { s += e[i]; ++n; }
  const double pl0 = n ? s / n : 0.95;
  std::size_t im = 0;
  for (std::size_t i = 1; i < x.size(); ++i)
    if (std::fabs(e[i] - 0.5 * pl0) < std::fabs(e[im] - 0.5 * pl0)) im = i;
  const double mu0 = x[im];
  auto chi2 = [&](const double* p) {
    double t = 0;
    for (std::size_t i = 0; i < x.size(); ++i) { const double r = (e[i] - model(x[i], p[0], p[1], p[2])) / w[i]; t += r * r; }
    return t;
  };
  const double start[3] = {mu0, 0.15 * mu0, pl0}, lo[3] = {0.0, 1e-4, 0.0}, hi[3] = {INFINITY, INFINITY, 1.0};
  const auto [p, fval] = minimise(chi2, start, lo, hi);
  (void)fval;
  return {p[0], p[1], p[2]};
}

// trigger_turnon.fit_turn_on_ml: binomial likelihood over every bin with entries, two starts, the better one
Fit mlFit(const std::vector<double>& c, const std::vector<double>& num, const std::vector<double>& den) {
  std::vector<double> x, k, n;
  for (std::size_t i = 0; i < c.size(); ++i) if (den[i] > 0) { x.push_back(c[i]); k.push_back(num[i]); n.push_back(den[i]); }
  if (x.size() < 6) return {};
  Fit s0 = chi2Fit(c, num, den);
  if (!s0.ok()) {
    std::vector<double> xs = x;
    std::sort(xs.begin(), xs.end());
    const std::size_t m = xs.size() / 2;
    s0 = {xs.size() % 2 ? xs[m] : 0.5 * (xs[m - 1] + xs[m]), 3.0, 0.95};
  }
  auto nll = [&](const double* p) {
    double t = 0;
    for (std::size_t i = 0; i < x.size(); ++i) {
      const double q = std::clamp(model(x[i], p[0], p[1], p[2]), 1e-9, 1 - 1e-9);
      t -= k[i] * std::log(q) + (n[i] - k[i]) * std::log(1 - q);
    }
    return t;
  };
  const double lo[3] = {0.0, 0.3, 0.0}, hi[3] = {INFINITY, INFINITY, 1.0};
  const double a[3] = {s0.mu, s0.sigma, s0.plateau}, b[3] = {s0.mu, std::max(s0.sigma, 3.0), 0.99};
  const auto ra = minimise(nll, a, lo, hi), rb = minimise(nll, b, lo, hi);
  const auto& best = ra.second <= rb.second ? ra.first : rb.first;
  return {best[0], best[1], best[2]};
}
}  // namespace

class TriggerTurnOnCalibrator final : public Gaudi::Algorithm {
public:
  using Gaudi::Algorithm::Algorithm;

  StatusCode initialize() override {
    StatusCode sc = Gaudi::Algorithm::initialize();
    if (sc.isFailure()) return sc;
    if (m_output.value().empty()) return error() << "OutputFile must be set" << endmsg, StatusCode::FAILURE;
    try {
      if (m_mode.value() == "Fill") return fill();
      if (m_mode.value() == "Fit") return fit();
    } catch (const std::exception& e) {
      return error() << e.what() << endmsg, StatusCode::FAILURE;
    }
    return error() << "Mode must be Fill or Fit, got '" << m_mode.value() << "'" << endmsg, StatusCode::FAILURE;
  }
  StatusCode execute(const EventContext&) const override { return StatusCode::SUCCESS; }

private:
  // ---------------------------------------------------------------------------------------------- Fill ---
  StatusCode fill() {
    if (m_inputFiles.value().empty()) return error() << "Fill needs InputFiles" << endmsg, StatusCode::FAILURE;
    // pedestal [slab][chip][channel][sca] as the table gives it (no masking); MPV [slab][chip][channel], 0 < MPV <= 100
    std::vector<double> ped(static_cast<std::size_t>(kSlbDepth) * kSkirocsPerAsu * kChannelsInSkiroc * kScasInSkiroc, kNaN);
    std::vector<double> mpv(static_cast<std::size_t>(kSlbDepth) * kSkirocsPerAsu * kChannelsInSkiroc, kNaN);
    for (const auto& row : table(m_pedFile.value())) {
      if (row.size() < 3 + 3 * kScasInSkiroc) continue;
      const int s = static_cast<int>(row[0]), c = static_cast<int>(row[1]), ch = static_cast<int>(row[2]);
      if (s < 0 || s >= kSlbDepth || c < 0 || c >= kSkirocsPerAsu || ch < 0 || ch >= kChannelsInSkiroc) continue;
      for (int k = 0; k < kScasInSkiroc; ++k) ped[((s * kSkirocsPerAsu + c) * kChannelsInSkiroc + ch) * kScasInSkiroc + k] = row[3 + 3 * k];
    }
    for (const auto& row : table(m_mipFile.value())) {
      if (row.size() < 4) continue;
      const int s = static_cast<int>(row[0]), c = static_cast<int>(row[1]), ch = static_cast<int>(row[2]);
      if (row[3] > 0 && row[3] <= 100.0 && s >= 0 && s < kSlbDepth && c >= 0 && c < kSkirocsPerAsu && ch >= 0 && ch < kChannelsInSkiroc)
        mpv[(s * kSkirocsPerAsu + c) * kChannelsInSkiroc + ch] = row[3];
    }
    std::vector<double> adcNum(kNAdc, 0.), adcDen(kNAdc, 0.), mipNum(kNMip, 0.), mipDen(kNMip, 0.);
    std::vector<double> slabNum(kSlbDepth * kNAdc, 0.), slabDen(kSlbDepth * kNAdc, 0.);
    struct Buf {
      int badbcid[kSlbDepth][kSkirocsPerAsu][kScasInSkiroc];
      int adcHigh[kSlbDepth][kSkirocsPerAsu][kScasInSkiroc][kChannelsInSkiroc];
      int hitHigh[kSlbDepth][kSkirocsPerAsu][kScasInSkiroc][kChannelsInSkiroc];
    };
    auto d = std::make_unique<Buf>();
    long long nSamples = 0, nAcq = 0;
    for (const auto& path : m_inputFiles.value()) {
      std::unique_ptr<TFile> f(TFile::Open(path.c_str(), "READ"));
      if (!f || f->IsZombie()) return error() << "cannot open " << path << endmsg, StatusCode::FAILURE;
      auto* t = dynamic_cast<TTree*>(f->Get(m_treeName.value().c_str()));
      if (!t) return error() << path << ": no tree " << m_treeName.value() << endmsg, StatusCode::FAILURE;
      t->SetBranchStatus("*", false);
      for (const char* b : {"badbcid", "adc_high", "hitbit_high"}) t->SetBranchStatus(b, true);
      t->SetBranchAddress("badbcid", d->badbcid);
      t->SetBranchAddress("adc_high", d->adcHigh);
      t->SetBranchAddress("hitbit_high", d->hitHigh);
      const Long64_t nEnt = m_perChunk.value() > 0 ? std::min<Long64_t>(t->GetEntries(), m_perChunk.value()) : t->GetEntries();
      for (Long64_t e = 0; e < nEnt; ++e) {
        t->GetEntry(e);
        ++nAcq;
        for (int s = 0; s < kSlbDepth; ++s)
          for (int c = 0; c < kSkirocsPerAsu; ++c)
            for (int ch = 0; ch < kChannelsInSkiroc; ++ch) {
              int best = 0;
              double amp = -INFINITY;
              bool seen = false;
              for (int k = 0; k < kScasInSkiroc; ++k) {   // first SCA with the largest valid amplitude (np.argmax)
                const int adc = d->adcHigh[s][c][k][ch];
                const double ps = static_cast<double>(adc) - ped[((s * kSkirocsPerAsu + c) * kChannelsInSkiroc + ch) * kScasInSkiroc + k];
                const bool valid = adc > 0 && std::isfinite(ps) && d->hitHigh[s][c][k][ch] >= 0 && d->badbcid[s][c][k] == 0;
                const double v = valid ? ps : -INFINITY;
                if (v > amp) { amp = v; best = k; }
              }
              const int adcB = d->adcHigh[s][c][best][ch];
              const double psB = static_cast<double>(adcB) - ped[((s * kSkirocsPerAsu + c) * kChannelsInSkiroc + ch) * kScasInSkiroc + best];
              seen = adcB > 0 && std::isfinite(psB) && d->hitHigh[s][c][best][ch] >= 0 && d->badbcid[s][c][best] == 0;
              const double m = mpv[(s * kSkirocsPerAsu + c) * kChannelsInSkiroc + ch];
              if (!seen || !std::isfinite(m) || !std::isfinite(amp)) continue;
              ++nSamples;
              const double fired = d->hitHigh[s][c][best][ch] == 1 ? 1.0 : 0.0;
              const int ia = binOf(amp, 0.0, 2.0, kNAdc);
              if (ia >= 0) {
                adcNum[ia] += fired; adcDen[ia] += 1;
                slabNum[s * kNAdc + ia] += fired; slabDen[s * kNAdc + ia] += 1;
              }
              const int im = binOf(amp / m, 0.0, 0.1, kNMip);
              if (im >= 0) { mipNum[im] += fired; mipDen[im] += 1; }
            }
      }
      info() << path << ": " << nAcq << " acquisitions, " << nSamples << " channel-acquisitions" << endmsg;
    }
    std::ofstream out(m_output.value());
    if (!out) return error() << "cannot write " << m_output.value() << endmsg, StatusCode::FAILURE;
    out << "# TriggerTurnOnCalibrator Fill: " << nAcq << " acquisitions, " << nSamples << " channel-acquisitions\n"
        << "# rows: axis bin num den; axis adc (0-160 by 2), mip (0-5 by 0.1), adc_slab<N>\n";
    auto dump = [&](const std::string& name, const double* num, const double* den, int nb) {
      for (int i = 0; i < nb; ++i) if (den[i] > 0) out << name << ' ' << i << ' ' << num[i] << ' ' << den[i] << '\n';
    };
    dump("adc", adcNum.data(), adcDen.data(), kNAdc);
    dump("mip", mipNum.data(), mipDen.data(), kNMip);
    for (int s = 0; s < kSlbDepth; ++s) dump("adc_slab" + std::to_string(s), &slabNum[s * kNAdc], &slabDen[s * kNAdc], kNAdc);
    return StatusCode::SUCCESS;
  }

  // ----------------------------------------------------------------------------------------------- Fit ---
  StatusCode fit() {
    if (m_fillFiles.value().empty()) return error() << "Fit needs FillFiles" << endmsg, StatusCode::FAILURE;
    std::map<std::string, std::pair<std::vector<double>, std::vector<double>>> h;
    auto get = [&](const std::string& name) -> auto& {
      auto& p = h[name];
      if (p.first.empty()) { const int nb = name == "mip" ? kNMip : kNAdc; p.first.assign(nb, 0.); p.second.assign(nb, 0.); }
      return p;
    };
    for (const auto& path : m_fillFiles.value()) {
      std::ifstream in(siwecal::resolveDataPath(path));
      std::string line;
      while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream ss(line);
        std::string name;
        int i;
        double num, den;
        if (!(ss >> name >> i >> num >> den)) continue;
        auto& p = get(name);
        p.first[i] += num;
        p.second[i] += den;
      }
    }
    auto centres = [](double w, int nb) { std::vector<double> c(nb); for (int i = 0; i < nb; ++i) c[i] = (i + 0.5) * w; return c; };
    const auto cAdc = centres(2.0, kNAdc), cMip = centres(0.1, kNMip);
    const Fit fMip = chi2Fit(cMip, get("mip").first, get("mip").second);
    const Fit fAdc = chi2Fit(cAdc, get("adc").first, get("adc").second);
    std::ofstream out(m_output.value());
    if (!out) return error() << "cannot write " << m_output.value() << endmsg, StatusCode::FAILURE;
    out << "# trigger turn-on, " << m_label.value() << " (TriggerTurnOnCalibrator)\n"
        << "# P(x) = plateau * 0.5 * (1 + erf((x - mu) / (sqrt(2) sigma))); x = best-SCA amplitude above the pedestal\n"
        << "#name mu sigma plateau\n";
    char b[160];
    std::snprintf(b, sizeof b, "set_mip %.6f %.6f %.6f\nset_adc %.6f %.6f %.6f\n", fMip.mu, fMip.sigma, fMip.plateau,
                  fAdc.mu, fAdc.sigma, fAdc.plateau);
    out << b;
    info() << "set: MIP mu " << fMip.mu << " sigma " << fMip.sigma << " plateau " << fMip.plateau << "; ADC mu " << fAdc.mu << endmsg;
    for (int s = 0; s < kSlbDepth; ++s) {
      auto& p = get("adc_slab" + std::to_string(s));
      if (std::accumulate(p.second.begin(), p.second.end(), 0.0) < m_minSlab.value()) continue;
      const Fit f = mlFit(cAdc, p.first, p.second);
      if (!f.ok()) continue;
      std::snprintf(b, sizeof b, "slab%d %.6f %.6f %.6f\n", s, f.mu, f.sigma, f.plateau);
      out << b;
    }
    info() << "wrote " << m_output.value() << endmsg;
    return StatusCode::SUCCESS;
  }

  // ------------------------------------------------------------------------------------------- helpers ---
  // numpy.digitize(x, edges) - 1 for edges lo + i * w (as numpy.arange builds them); -1 outside
  static int binOf(double x, double lo, double w, int nb) {
    if (!(x >= lo)) return -1;
    int i = static_cast<int>(std::floor((x - lo) / w));
    while (i > 0 && x < lo + i * w) --i;              // exact edge semantics of arange-built edges
    while (i < nb && x >= lo + (i + 1) * w) ++i;
    return i < nb ? i : -1;
  }

  static std::vector<std::vector<double>> table(const std::string& name) {
    std::vector<std::vector<double>> rows;
    std::ifstream in(siwecal::resolveDataPath(name));
    std::string line;
    while (std::getline(in, line)) {
      if (line.empty() || line[0] == '#') continue;
      std::istringstream ss(line);
      std::vector<double> r;
      for (std::string tok; ss >> tok;) r.push_back(std::strtod(tok.c_str(), nullptr));   // reads '-nan' too
      if (!r.empty()) rows.push_back(std::move(r));
    }
    return rows;
  }

  Gaudi::Property<std::string> m_mode{this, "Mode", "Fill", "Fill (one run -> turn-on histograms) | Fit (-> parameters)"};
  Gaudi::Property<std::vector<std::string>> m_inputFiles{this, "InputFiles", {}, "Fill: decoded chunks of one run"};
  Gaudi::Property<std::string> m_treeName{this, "TreeName", "siwecaldecoded", "Fill: input tree"};
  Gaudi::Property<long long> m_perChunk{this, "AcquisitionsPerChunk", 40, "Fill: first N entries of each chunk (0 = all)"};
  Gaudi::Property<std::string> m_pedFile{this, "PedestalFile", "", "Fill: high-gain pedestal table of the set"};
  Gaudi::Property<std::string> m_mipFile{this, "MipFile", "", "Fill: high-gain MIP table of the set"};
  Gaudi::Property<std::vector<std::string>> m_fillFiles{this, "FillFiles", {}, "Fit: Fill outputs (summed)"};
  Gaudi::Property<double> m_minSlab{this, "MinSlabEntries", 2000, "Fit: entries for a slab to get its own turn-on"};
  Gaudi::Property<std::string> m_label{this, "Label", "", "Fit: header text"};
  Gaudi::Property<std::string> m_output{this, "OutputFile", "", "Fill: histogram text file; Fit: the parameters"};
};

DECLARE_COMPONENT(TriggerTurnOnCalibrator)
