// OccupancySagCalibrator -- the measured chip baseline-sag map B(Q_chip, Q_slab) that AdcDigitizer
// (OccupancySagTable) applies to the simulation, produced from the electron runs of a threshold set.
// Gaudi port of analysis/cm_sag_collect.py + analysis/sag_table.py (retired), same selection and same table.
//
// Mode=Fill   one run: InputFiles = its siwecaldecoded chunks. Per acquisition, slab and chip-SCA column:
//   valid    chip present (chipid >= 0), column < nColumns, and not following another column of the same chip
//            within 1-3 BCIDs (retriggers);
//   good     channel of a valid column with finite high- and low-gain pedestal (PedestalFile/PedestalFileLowGain,
//            the th210 tables) and adc_high > 0;
//   r, rl    adc_high - pedestal_HG, adc_low - pedestal_LG (same SCA);
//   far      good, not fired (hitbit_high == 0) and >= 2 pads (Chebyshev distance, pad map of the slab) from every
//            fired good channel of the chip-SCA;
//   B        median r of the far channels (the baseline of the chip-SCA without signal);
//   q_chip   charge of the chip-SCA = sum over its fired good channels of rl / GainRatio (HG ADC);
//   q_slab   charge of the whole slab in the BCID window +-1 of the column (all valid columns), minus q_chip.
//   A record (B, q_chip, q_slab) is kept when B is finite and the column has > 8 good channels; records are summed
//   into the (QChipEdges x QSlabEdges) bins: count, sum B, sum q_chip, sum q_slab -> OutputFile (text).
// Mode=Table  FillFiles = the Fill outputs of the runs of one set -> OutputFile, occupancy_sag_<set>.txt:
//   mean B per bin with >= MinRecords records, bin centre = record-weighted mean charge over the filled bins of the
//   row / column, empty rows and columns dropped, empty bins filled from the nearest filled bin of the same Q_chip
//   row, then of the same Q_slab column. Header 'qchip', 'qslab', one row of B [HG ADC] per Q_chip centre.
//
// Values follow the Python reference in single precision where it was (B, q_chip, q_slab are float32 records), so
// the tables agree to their printed precision (tests/control/test_occupancy_sag.py).
#include "Gaudi/Algorithm.h"
#include "Gaudi/Property.h"
#include "GaudiKernel/MsgStream.h"

#include "siwecal/DataPath.h"
#include "siwecal/PadMap.hh"
#include "siwecal/SlbFrameDecoder.h"  // kSlbDepth, kSkirocsPerAsu, kScasInSkiroc, kChannelsInSkiroc

#include "TFile.h"
#include "TTree.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace {
using k4siwecal::kChannelsInSkiroc;
using k4siwecal::kScasInSkiroc;
using k4siwecal::kSkirocsPerAsu;
using k4siwecal::kSlbDepth;
constexpr float kNaN = std::numeric_limits<float>::quiet_NaN();
constexpr int kNBcid = 4096;

// pedestal[slab][chip][sca][channel], NaN where the table has no usable fit (mean <= 0 or width <= 0)
using PedTable = std::vector<float>;
inline std::size_t pidx(int s, int c, int k, int ch) {
  return ((static_cast<std::size_t>(s) * kSkirocsPerAsu + c) * kScasInSkiroc + k) * kChannelsInSkiroc + ch;
}

// numpy.digitize(x, edges) - 1, clipped to [0, nbins - 1]
int binOf(float x, const std::vector<double>& edges) {
  const int n = static_cast<int>(edges.size()) - 1;
  const int i = static_cast<int>(std::upper_bound(edges.begin(), edges.end(), static_cast<double>(x)) - edges.begin()) - 1;
  return std::clamp(i, 0, n - 1);
}
}  // namespace

class OccupancySagCalibrator final : public Gaudi::Algorithm {
public:
  using Gaudi::Algorithm::Algorithm;

  StatusCode initialize() override {
    StatusCode sc = Gaudi::Algorithm::initialize();
    if (sc.isFailure()) return sc;
    if (m_output.value().empty()) return error() << "OutputFile must be set" << endmsg, StatusCode::FAILURE;
    try {
      if (m_mode.value() == "Fill") return fill();
      if (m_mode.value() == "Table") return table();
    } catch (const std::exception& e) {
      return error() << e.what() << endmsg, StatusCode::FAILURE;
    }
    return error() << "Mode must be Fill or Table, got '" << m_mode.value() << "'" << endmsg, StatusCode::FAILURE;
  }

  StatusCode execute(const EventContext&) const override { return StatusCode::SUCCESS; }

private:
  // ------------------------------------------------------------------------------------------------ Fill ---
  StatusCode fill() {
    if (m_inputFiles.value().empty()) return error() << "Fill needs InputFiles" << endmsg, StatusCode::FAILURE;
    const PedTable pedHg = loadPedestals(m_pedHg.value()), pedLg = loadPedestals(m_pedLg.value());
    // far-from-signal neighbourhood (Chebyshev distance < 2.5 pitches), per slab through its pad map
    std::vector<siwecal::PadEntry> padDefault;
    std::map<int, std::vector<siwecal::PadEntry>> padOverrides;
    std::string err;
    if (!siwecal::loadPadMap(m_padMap.value(), padDefault, err) ||
        !siwecal::loadPadMapOverrides(m_padMapOverrides.value(), padOverrides, err))
      return error() << err << endmsg, StatusCode::FAILURE;
    const auto adjDefault = adjacency(padDefault);
    std::map<int, std::vector<char>> adjOverride;
    for (const auto& [slab, pads] : padOverrides) adjOverride[slab] = adjacency(pads);

    const std::size_t nq = m_qcEdges.value().size() - 1, ns = m_qsEdges.value().size() - 1;
    std::vector<double> n(nq * ns, 0.), sB(nq * ns, 0.), sQc(nq * ns, 0.), sQs(nq * ns, 0.);
    long long nAcq = 0, nRec = 0;
    const float k = static_cast<float>(m_gainRatio.value());

    struct Buf {
      int chipid[kSlbDepth][kSkirocsPerAsu];
      int nColumns[kSlbDepth][kSkirocsPerAsu];
      int bcid[kSlbDepth][kSkirocsPerAsu][kScasInSkiroc];
      int adcHigh[kSlbDepth][kSkirocsPerAsu][kScasInSkiroc][kChannelsInSkiroc];
      int adcLow[kSlbDepth][kSkirocsPerAsu][kScasInSkiroc][kChannelsInSkiroc];
      int hitHigh[kSlbDepth][kSkirocsPerAsu][kScasInSkiroc][kChannelsInSkiroc];
    };
    auto buf = std::make_unique<Buf>();

    for (const auto& path : m_inputFiles.value()) {
      std::unique_ptr<TFile> f(TFile::Open(path.c_str(), "READ"));
      if (!f || f->IsZombie()) return error() << "cannot open " << path << endmsg, StatusCode::FAILURE;
      auto* t = dynamic_cast<TTree*>(f->Get(m_treeName.value().c_str()));
      if (!t) return error() << path << ": no tree " << m_treeName.value() << endmsg, StatusCode::FAILURE;
      t->SetBranchStatus("*", false);
      for (const char* b : {"chipid", "nColumns", "bcid", "adc_high", "adc_low", "hitbit_high"}) t->SetBranchStatus(b, true);
      t->SetBranchAddress("chipid", buf->chipid);
      t->SetBranchAddress("nColumns", buf->nColumns);
      t->SetBranchAddress("bcid", buf->bcid);
      t->SetBranchAddress("adc_high", buf->adcHigh);
      t->SetBranchAddress("adc_low", buf->adcLow);
      t->SetBranchAddress("hitbit_high", buf->hitHigh);
      const Long64_t nEnt = t->GetEntries();
      for (Long64_t e = 0; e < nEnt; ++e) {
        if (m_maxAcq.value() > 0 && nAcq >= m_maxAcq.value()) break;
        t->GetEntry(e);
        ++nAcq;
        nRec += acquisition(*buf, pedHg, pedLg, adjDefault, adjOverride, k, n, sB, sQc, sQs);
      }
      info() << path << ": " << nAcq << " acquisitions, " << nRec << " chip-SCA records" << endmsg;
    }
    // text accumulators: 'qchip_edges', 'qslab_edges', then 'i j n sumB sumQchip sumQslab' per bin with records
    std::ofstream out(m_output.value());
    if (!out) return error() << "cannot write " << m_output.value() << endmsg, StatusCode::FAILURE;
    out << "# OccupancySagCalibrator Fill: " << nAcq << " acquisitions, " << nRec << " records\n";
    out << "qchip_edges";
    for (double x : m_qcEdges.value()) out << ' ' << fmt17(x);
    out << "\nqslab_edges";
    for (double x : m_qsEdges.value()) out << ' ' << fmt17(x);
    out << '\n';
    for (std::size_t i = 0; i < nq; ++i)
      for (std::size_t j = 0; j < ns; ++j) {
        const std::size_t b = i * ns + j;
        if (n[b] > 0)
          out << i << ' ' << j << ' ' << fmt17(n[b]) << ' ' << fmt17(sB[b]) << ' ' << fmt17(sQc[b]) << ' '
              << fmt17(sQs[b]) << '\n';
      }
    info() << "wrote " << m_output.value() << endmsg;
    return StatusCode::SUCCESS;
  }

  // one acquisition: the records of every valid chip-SCA column; returns how many
  long long acquisition(const auto& d, const PedTable& pedHg, const PedTable& pedLg, const std::vector<char>& adjDefault,
                        const std::map<int, std::vector<char>>& adjOverride, float k, std::vector<double>& n,
                        std::vector<double>& sB, std::vector<double>& sQc, std::vector<double>& sQs) const {
    const std::size_t ns = m_qsEdges.value().size() - 1;
    long long nRec = 0;
    for (int s = 0; s < kSlbDepth; ++s) {
      const auto ito = adjOverride.find(s);
      const std::vector<char>& A = ito == adjOverride.end() ? adjDefault : ito->second;
      // per column: valid, its charge and its record (if any)
      struct Col { bool valid = false; int bcid = 0; float q = 0.f; float B = kNaN; int nGood = 0; };
      std::array<std::array<Col, kScasInSkiroc>, kSkirocsPerAsu> cols{};
      std::vector<double> H(kNBcid, 0.);   // charge of the slab per BCID
      for (int c = 0; c < kSkirocsPerAsu; ++c) {
        const int cid = d.chipid[s][c];
        if (cid < 0) continue;
        const int cc = std::min(cid, kSkirocsPerAsu - 1);
        const int nCol = d.nColumns[s][c];
        bool pre[kScasInSkiroc];
        for (int q = 0; q < kScasInSkiroc; ++q) pre[q] = q < nCol;
        for (int q = 0; q < kScasInSkiroc; ++q) {
          if (!pre[q]) continue;
          bool retrig = false;   // another column of the chip 1-3 BCIDs before this one
          for (int p = 0; p < kScasInSkiroc && !retrig; ++p) {
            if (!pre[p]) continue;
            const int dbc = d.bcid[s][c][q] - d.bcid[s][c][p];
            retrig = dbc >= 1 && dbc <= 3;
          }
          if (retrig) continue;
          Col& col = cols[c][q];
          col.valid = true;
          col.bcid = d.bcid[s][c][q];
          float r[kChannelsInSkiroc], rl[kChannelsInSkiroc];
          bool good[kChannelsInSkiroc], fired[kChannelsInSkiroc];
          for (int ch = 0; ch < kChannelsInSkiroc; ++ch) {
            const float P = pedHg[pidx(s, cc, q, ch)], PL = pedLg[pidx(s, cc, q, ch)];
            const int adc = d.adcHigh[s][c][q][ch];
            good[ch] = std::isfinite(P) && std::isfinite(PL) && adc > 0;
            r[ch] = static_cast<float>(adc) - P;
            rl[ch] = static_cast<float>(d.adcLow[s][c][q][ch]) - PL;
            fired[ch] = good[ch] && d.hitHigh[s][c][q][ch] != 0;
            col.nGood += good[ch];
          }
          double q2 = 0.;
          for (int ch = 0; ch < kChannelsInSkiroc; ++ch)
            if (fired[ch]) q2 += static_cast<double>(rl[ch] / k);
          col.q = static_cast<float>(q2);
          std::vector<float> far;
          for (int ch = 0; ch < kChannelsInSkiroc; ++ch) {
            if (!good[ch] || d.hitHigh[s][c][q][ch] != 0) continue;
            bool near = false;
            for (int o = 0; o < kChannelsInSkiroc && !near; ++o)
              near = fired[o] && A[(static_cast<std::size_t>(cc) * kChannelsInSkiroc + o) * kChannelsInSkiroc + ch];
            if (!near) far.push_back(r[ch]);
          }
          if (!far.empty()) {
            std::sort(far.begin(), far.end());
            const std::size_t m = far.size() / 2;
            col.B = far.size() % 2 ? far[m] : (far[m - 1] + far[m]) / 2.f;
          }
          if (col.bcid >= 0 && col.bcid < kNBcid) H[col.bcid] += col.q;
        }
      }
      for (int c = 0; c < kSkirocsPerAsu; ++c)
        for (int q = 0; q < kScasInSkiroc; ++q) {
          const Col& col = cols[c][q];
          if (!col.valid || !std::isfinite(col.B) || col.nGood <= 8) continue;
          double w = 0.;   // slab charge in BCID +-1
          for (int b = col.bcid - 1; b <= col.bcid + 1; ++b)
            if (b >= 0 && b < kNBcid) w += H[b];
          const float qc = col.q, qs = static_cast<float>(w - static_cast<double>(col.q));
          const std::size_t bin = static_cast<std::size_t>(binOf(qc, m_qcEdges.value())) * ns +
                                  static_cast<std::size_t>(binOf(qs, m_qsEdges.value()));
          n[bin] += 1.;
          sB[bin] += col.B;
          sQc[bin] += qc;
          sQs[bin] += qs;
          ++nRec;
        }
    }
    return nRec;
  }

  // ----------------------------------------------------------------------------------------------- Table ---
  StatusCode table() {
    if (m_fillFiles.value().empty()) return error() << "Table needs FillFiles" << endmsg, StatusCode::FAILURE;
    std::vector<double> qcE, qsE, n, sB, sQc, sQs;
    for (const auto& path : m_fillFiles.value()) {
      std::ifstream in(siwecal::resolveDataPath(path));
      std::string line;
      std::vector<double> fq, fs;
      while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream ss(line);
        std::string tag;
        ss >> tag;
        if (tag == "qchip_edges" || tag == "qslab_edges") {
          auto& v = tag == "qchip_edges" ? fq : fs;
          for (double x; ss >> x;) v.push_back(x);
          if (!fq.empty() && !fs.empty() && n.empty()) {
            qcE = fq;
            qsE = fs;
            const std::size_t sz = (qcE.size() - 1) * (qsE.size() - 1);
            n.assign(sz, 0.); sB.assign(sz, 0.); sQc.assign(sz, 0.); sQs.assign(sz, 0.);
          }
          continue;
        }
        if (fq != qcE || fs != qsE) return error() << path << ": different bin edges" << endmsg, StatusCode::FAILURE;
        std::istringstream row(line);
        std::size_t i, j;
        double a, b, c, e;
        row >> i >> j >> a >> b >> c >> e;
        const std::size_t bin = i * (qsE.size() - 1) + j;
        n[bin] += a; sB[bin] += b; sQc[bin] += c; sQs[bin] += e;
      }
    }
    const std::size_t nq = qcE.size() - 1, ns = qsE.size() - 1;
    const double minN = m_minRecords.value();
    auto ok = [&](std::size_t i, std::size_t j) { return n[i * ns + j] >= minN; };
    // bin centres over the filled bins of each row / column; empty rows and columns dropped
    std::vector<double> xc, yc;
    std::vector<std::size_t> rows, colsKept;
    for (std::size_t i = 0; i < nq; ++i) {
      double num = 0., den = 0.;
      for (std::size_t j = 0; j < ns; ++j) if (ok(i, j)) { num += sQc[i * ns + j]; den += n[i * ns + j]; }
      if (den > 0) { rows.push_back(i); xc.push_back(num / den); }
    }
    for (std::size_t j = 0; j < ns; ++j) {
      double num = 0., den = 0.;
      for (std::size_t i = 0; i < nq; ++i) if (ok(i, j)) { num += sQs[i * ns + j]; den += n[i * ns + j]; }
      if (den > 0) { colsKept.push_back(j); yc.push_back(num / den); }
    }
    const std::size_t R = rows.size(), C = colsKept.size();
    std::vector<double> tab(R * C, std::numeric_limits<double>::quiet_NaN());
    std::vector<char> filled(R * C, 0);
    for (std::size_t r = 0; r < R; ++r)
      for (std::size_t c = 0; c < C; ++c) {
        const std::size_t b = rows[r] * ns + colsKept[c];
        if (n[b] >= minN) { tab[r * C + c] = sB[b] / n[b]; filled[r * C + c] = 1; }
      }
    auto nearest = [](const std::vector<std::size_t>& idx, std::size_t k) {   // first of the closest (argmin)
      std::size_t best = idx.front();
      for (std::size_t v : idx) {
        const long dv = std::labs(static_cast<long>(v) - static_cast<long>(k));
        const long db = std::labs(static_cast<long>(best) - static_cast<long>(k));
        if (dv < db) best = v;
      }
      return best;
    };
    for (std::size_t r = 0; r < R; ++r) {   // along Q_slab from the nearest filled bin of the row
      std::vector<std::size_t> f;
      for (std::size_t c = 0; c < C; ++c) if (filled[r * C + c]) f.push_back(c);
      if (f.empty()) continue;
      for (std::size_t c = 0; c < C; ++c) if (!filled[r * C + c]) tab[r * C + c] = tab[r * C + nearest(f, c)];
    }
    for (std::size_t c = 0; c < C; ++c) {   // rows still empty: along Q_chip
      std::vector<std::size_t> f;
      for (std::size_t r = 0; r < R; ++r) if (!std::isnan(tab[r * C + c])) f.push_back(r);
      if (f.empty()) continue;
      for (std::size_t r = 0; r < R; ++r) if (std::isnan(tab[r * C + c])) tab[r * C + c] = tab[nearest(f, r) * C + c];
    }
    std::ofstream out(m_output.value());
    if (!out) return error() << "cannot write " << m_output.value() << endmsg, StatusCode::FAILURE;
    out << "# Baseline sag B [HG ADC] of signal-free channels, " << m_label.value() << "\n"
        << "# (OccupancySagCalibrator, data_conversion/jobs/calibration/run_occupancy_sag.py). Rows: Q_chip centres;\n"
        << "# columns: Q_slab centres (charge of the other chips of the slab at the same BCID +-1). Interpolate\n"
        << "# bilinearly in ln(1+Q), clamp at the edges.\n";
    out << "qchip";
    for (double x : xc) out << ' ' << fixed(x, 1);
    out << "\nqslab";
    for (double y : yc) out << ' ' << fixed(y, 1);
    out << '\n';
    for (std::size_t r = 0; r < R; ++r) {
      for (std::size_t c = 0; c < C; ++c) out << (c ? " " : "") << fixed(tab[r * C + c], 3);
      out << '\n';
    }
    info() << "wrote " << m_output.value() << " (" << R << " x " << C << ")" << endmsg;
    return StatusCode::SUCCESS;
  }

  // ------------------------------------------------------------------------------------------- helpers ---
  PedTable loadPedestals(const std::string& name) const {
    PedTable ped(static_cast<std::size_t>(kSlbDepth) * kSkirocsPerAsu * kScasInSkiroc * kChannelsInSkiroc, kNaN);
    std::ifstream in(siwecal::resolveDataPath(name));
    std::string line;
    while (std::getline(in, line)) {
      if (line.empty() || line[0] == '#') continue;
      std::istringstream ss(line);
      int s, c, ch;
      if (!(ss >> s >> c >> ch)) continue;
      double v[45];
      int got = 0;
      // strtod, not operator>>: the tables hold '-nan' entries, which a stream refuses (and would drop the row)
      for (std::string tok; got < 45 && ss >> tok; ++got) v[got] = std::strtod(tok.c_str(), nullptr);
      if (got < 45 || s < 0 || s >= kSlbDepth || c < 0 || c >= kSkirocsPerAsu || ch < 0 || ch >= kChannelsInSkiroc)
        continue;
      for (int k = 0; k < kScasInSkiroc; ++k) {
        const double mean = v[3 * k], width = v[3 * k + 2];
        ped[pidx(s, c, k, ch)] = (mean > 0 && width > 0) ? static_cast<float>(mean) : kNaN;
      }
    }
    return ped;
  }

  // A[chip][o][ch] = pads o, ch of a chip within 2.5 pitches (Chebyshev), o != ch
  std::vector<char> adjacency(const std::vector<siwecal::PadEntry>& pads) const {
    std::vector<double> x(kSkirocsPerAsu * kChannelsInSkiroc, std::nan("")), y(x);
    for (const auto& p : pads)
      if (p.chip >= 0 && p.chip < kSkirocsPerAsu && p.channel >= 0 && p.channel < kChannelsInSkiroc) {
        x[p.chip * kChannelsInSkiroc + p.channel] = p.x;
        y[p.chip * kChannelsInSkiroc + p.channel] = p.y;
      }
    std::vector<char> A(static_cast<std::size_t>(kSkirocsPerAsu) * kChannelsInSkiroc * kChannelsInSkiroc, 0);
    const double lim = 2.5 * m_pitch.value();
    for (int c = 0; c < kSkirocsPerAsu; ++c)
      for (int a = 0; a < kChannelsInSkiroc; ++a)
        for (int b = 0; b < kChannelsInSkiroc; ++b) {
          const double dx = std::fabs(x[c * kChannelsInSkiroc + a] - x[c * kChannelsInSkiroc + b]);
          const double dy = std::fabs(y[c * kChannelsInSkiroc + a] - y[c * kChannelsInSkiroc + b]);
          const double d = std::max(dx, dy);
          A[(static_cast<std::size_t>(c) * kChannelsInSkiroc + a) * kChannelsInSkiroc + b] = d < lim && d > 0;
        }
    return A;
  }

  static std::string fmt17(double v) { char b[40]; std::snprintf(b, sizeof b, "%.17g", v); return b; }
  static std::string fixed(double v, int p) { char b[40]; std::snprintf(b, sizeof b, "%.*f", p, v); return b; }

  Gaudi::Property<std::string> m_mode{this, "Mode", "Fill", "Fill (one run -> bin accumulators) | Table (runs -> map)"};
  Gaudi::Property<std::vector<std::string>> m_inputFiles{this, "InputFiles", {}, "Fill: siwecaldecoded chunks of one run"};
  Gaudi::Property<std::string> m_treeName{this, "TreeName", "siwecaldecoded", "Fill: input tree"};
  Gaudi::Property<std::string> m_pedHg{this, "PedestalFile", "", "Fill: high-gain pedestal table (th210)"};
  Gaudi::Property<std::string> m_pedLg{this, "PedestalFileLowGain", "", "Fill: low-gain pedestal table (th210)"};
  Gaudi::Property<std::string> m_padMap{this, "PadMapDefaultFile", "fev10_rotate_chip_channel_x_y_mapping.txt",
                                        "Fill: default pad map (resolveDataPath)"};
  Gaudi::Property<std::vector<std::string>> m_padMapOverrides{this, "PadMapSlabOverrides", {},
                                                              "Fill: 'slab:path' pad maps of other slabs"};
  Gaudi::Property<double> m_gainRatio{this, "GainRatio", 0.0924,
                                      "Fill: LG->HG anchor k, charge = (adc_low - ped_LG) / k [HG ADC]"};
  Gaudi::Property<double> m_pitch{this, "PadPitchMm", 5.53, "Fill: pad pitch for the 2.5-pitch neighbourhood"};
  Gaudi::Property<long long> m_maxAcq{this, "MaxAcquisitions", 0, "Fill: stop after this many (0 = all)"};
  Gaudi::Property<std::vector<double>> m_qcEdges{this, "QChipEdges", defaultQcEdges(), "Q_chip bin edges [HG ADC]"};
  Gaudi::Property<std::vector<double>> m_qsEdges{this, "QSlabEdges", defaultQsEdges(), "Q_slab bin edges [HG ADC]"};
  Gaudi::Property<std::vector<std::string>> m_fillFiles{this, "FillFiles", {}, "Table: Fill outputs of the runs"};
  Gaudi::Property<double> m_minRecords{this, "MinRecords", 50, "Table: records for a bin to count as filled"};
  Gaudi::Property<std::string> m_label{this, "Label", "", "Table: header text (set, runs)"};
  Gaudi::Property<std::string> m_output{this, "OutputFile", "", "Fill: accumulator text file; Table: the map"};

  // 0, then 16 log-spaced edges 20 .. 15000 (Q_chip); 0, then 12 log-spaced 200 .. 40000 (Q_slab)
  static std::vector<double> logEdges(double lo, double hi, int n) {
    std::vector<double> e{0.};
    for (int i = 0; i < n; ++i) e.push_back(std::pow(10., std::log10(lo) + (std::log10(hi) - std::log10(lo)) * i / (n - 1)));
    return e;
  }
  static std::vector<double> defaultQcEdges() { return logEdges(20., 15000., 16); }
  static std::vector<double> defaultQsEdges() { return logEdges(200., 40000., 12); }
};

DECLARE_COMPONENT(OccupancySagCalibrator)
