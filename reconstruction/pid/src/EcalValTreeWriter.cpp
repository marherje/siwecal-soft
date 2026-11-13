/*
 * EcalValTreeWriter: the valtree, the flat per-event tree the analysis reads (analysis/final_panels.py,
 * siwecal_validation, the event viewer), written by the PID job itself. Port of
 * siwecal_common.edm4hep_pid.write_valtree, which re-read the EDM4hep file in Python after the job.
 *
 * One entry per event that the selection lets through (SelectionAlgorithm, e.g. EcalEventSelection: the same
 * events the IOSvc writer keeps; empty = every event):
 *   run, event, spill, bcid                       EventHeader (runNumber, eventNumber, weight, timeStamp)
 *   nhit_chan, nhit_slab, nhit_chip, sum_hg, sum_energy   counted / summed over the event's hits
 *   hit_slab, hit_chip, hit_chan, hit_sca [nhit_chan] /I, hit_hg, hit_lg, hit_energy, hit_x, hit_y, hit_z,
 *   hit_w_energy, hit_X0 [nhit_chan] /F        ECalHits and their parallel UserDataCollections
 *   <scalar> /D (is_shower /O), <per-layer>[NLayers] /D, mip<thr>_<scalar>   ECalPid shapeParameters, in the
 *                                                  EcalShowerVariables layout (EcalShowerVars.h)
 * Written to OutputFile.tmp and renamed at finalize, so a failed job leaves no truncated tree behind.
 * Validated against the Python writer: same events, every branch identical except sum_hg / sum_energy (float
 * summation order, < 1e-6 relative).
 */
#include "siwecal/EcalShowerVars.h"

#include "Gaudi/Algorithm.h"
#include "Gaudi/Property.h"
#include "GaudiKernel/IAlgExecStateSvc.h"
#include "GaudiKernel/MsgStream.h"
#include "k4FWCore/DataHandle.h"

#include "edm4hep/CalorimeterHitCollection.h"
#include "edm4hep/ClusterCollection.h"
#include "edm4hep/EventHeaderCollection.h"
#include "podio/UserDataCollection.h"

#include "TFile.h"
#include "TTree.h"

#include <algorithm>
#include <cstdio>
#include <memory>
#include <set>
#include <string>
#include <vector>

class EcalValTreeWriter final : public Gaudi::Algorithm {
public:
  using Gaudi::Algorithm::Algorithm;

  StatusCode initialize() override {
    StatusCode sc = Gaudi::Algorithm::initialize();
    if (sc.isFailure()) return sc;
    if (m_output.value().empty()) return error() << "OutputFile must be set" << endmsg, StatusCode::FAILURE;
    using k4FWCore::DataHandle;
    m_clusters = std::make_unique<DataHandle<edm4hep::ClusterCollection>>(m_clusterName.value(), Gaudi::DataHandle::Reader, this);
    m_hits = std::make_unique<DataHandle<edm4hep::CalorimeterHitCollection>>(m_hitName.value(), Gaudi::DataHandle::Reader, this);
    m_header = std::make_unique<DataHandle<edm4hep::EventHeaderCollection>>(m_headerName.value(), Gaudi::DataHandle::Reader, this);
    for (const auto& [n, c] : std::vector<std::pair<std::string, std::string>>{{"hit_chip", "ECalHitChip"}, {"hit_chan", "ECalHitChan"}, {"hit_sca", "ECalHitSca"}})
      m_ints.push_back({n, std::make_unique<DataHandle<podio::UserDataCollection<std::int32_t>>>(c, Gaudi::DataHandle::Reader, this)});
    for (const auto& [n, c] : std::vector<std::pair<std::string, std::string>>{{"hit_hg", "ECalHitHG"}, {"hit_lg", "ECalHitLG"}, {"hit_w_energy", "ECalHitWE"}, {"hit_X0", "ECalHitX0"}})
      m_floats.push_back({n, std::make_unique<DataHandle<podio::UserDataCollection<float>>>(c, Gaudi::DataHandle::Reader, this)});

    // the shapeParameters layout: scalars, per-layer blocks, then one scalar block per MIP threshold
    m_scalarNames = k4siwecal::scalarNames();
    m_layerNames = k4siwecal::perLayerNames();
    for (double t : m_mipThresholds.value()) m_prefixes.push_back(prefix(t));
    m_width = m_scalarNames.size() * (1 + m_prefixes.size()) + m_layerNames.size() * m_nLayers.value();

    m_file.reset(TFile::Open((m_output.value() + ".tmp").c_str(), "RECREATE"));
    if (!m_file || m_file->IsZombie()) return error() << "cannot write " << m_output.value() << endmsg, StatusCode::FAILURE;
    m_tree = new TTree(m_treeName.value().c_str(), m_treeName.value().c_str());
    for (const char* n : {"run", "event", "spill", "bcid"}) m_tree->Branch(n, &m_id[idIndex(n)], (std::string(n) + "/I").c_str());
    m_tree->Branch("nhit_chan", &m_nhit, "nhit_chan/I");
    m_tree->Branch("nhit_slab", &m_nslab, "nhit_slab/I");
    m_tree->Branch("nhit_chip", &m_nchip, "nhit_chip/I");
    m_tree->Branch("sum_hg", &m_sumHg, "sum_hg/F");
    m_tree->Branch("sum_energy", &m_sumE, "sum_energy/F");
    m_hitInt.assign(4, std::vector<int>(kMaxHits));
    m_hitFloat.assign(kNFloat, std::vector<float>(kMaxHits));
    const char* intNames[4] = {"hit_slab", "hit_chip", "hit_chan", "hit_sca"};
    for (int i = 0; i < 4; ++i) m_tree->Branch(intNames[i], m_hitInt[i].data(), (std::string(intNames[i]) + "[nhit_chan]/I").c_str());
    for (int i = 0; i < kNFloat; ++i) m_tree->Branch(kFloatNames[i], m_hitFloat[i].data(), (std::string(kFloatNames[i]) + "[nhit_chan]/F").c_str());
    const std::size_t nScal = m_scalarNames.size();
    m_scal.assign(nScal * (1 + m_prefixes.size()), 0.0);
    m_flag.assign(1 + m_prefixes.size(), 0);
    auto scalarBranches = [&](const std::string& pre, std::size_t block) {
      for (std::size_t i = 0; i < nScal; ++i) {
        const std::string n = pre.empty() ? m_scalarNames[i] : pre + "_" + m_scalarNames[i];
        if (m_scalarNames[i] == "is_shower") m_tree->Branch(n.c_str(), &m_flag[block], (n + "/O").c_str());
        else m_tree->Branch(n.c_str(), &m_scal[block * nScal + i], (n + "/D").c_str());
      }
    };
    scalarBranches("", 0);
    m_layers.assign(m_layerNames.size() * m_nLayers.value(), 0.0);
    for (std::size_t b = 0; b < m_layerNames.size(); ++b)
      m_tree->Branch(m_layerNames[b].c_str(), &m_layers[b * m_nLayers.value()],
                     (m_layerNames[b] + "[" + std::to_string(m_nLayers.value()) + "]/D").c_str());
    for (std::size_t p = 0; p < m_prefixes.size(); ++p) scalarBranches(m_prefixes[p], p + 1);
    return StatusCode::SUCCESS;
  }

  StatusCode execute(const EventContext& ctx) const override {
    if (!m_selection.value().empty() && !algExecStateSvc()->algExecState(m_selection.value(), ctx).filterPassed())
      return StatusCode::SUCCESS;
    const auto* clusters = m_clusters->get();
    const auto* hits = m_hits->get();
    const auto* header = m_header->get();
    if (clusters->size() < 1) return error() << "no ECalPid cluster in the event" << endmsg, StatusCode::FAILURE;
    const auto par = clusters->at(0).getShapeParameters();
    if (par.size() != m_width)
      return error() << "shapeParameters has " << par.size() << " entries, the layout of NLayers / MipThresholds "
                     << m_width << endmsg, StatusCode::FAILURE;
    const auto h = header->at(0);
    m_id[0] = static_cast<int>(h.getRunNumber());
    m_id[1] = static_cast<int>(h.getEventNumber());
    m_id[2] = static_cast<int>(static_cast<long long>(h.getWeight()));
    m_id[3] = static_cast<int>(h.getTimeStamp());
    const std::size_t n = hits->size();
    if (n > kMaxHits) return error() << n << " hits, more than " << kMaxHits << endmsg, StatusCode::FAILURE;
    std::vector<const podio::UserDataCollection<std::int32_t>*> ints;
    for (const auto& [name, hd] : m_ints) ints.push_back(hd->get());
    std::vector<const podio::UserDataCollection<float>*> floats;
    for (const auto& [name, hd] : m_floats) floats.push_back(hd->get());
    std::set<int> slabs;
    std::set<long long> chips;
    double sumHg = 0, sumE = 0;
    for (std::size_t i = 0; i < n; ++i) {
      const auto hit = (*hits)[i];
      const int slab = hit.getType();
      const int chip = (*ints[0])[i];
      m_hitInt[0][i] = slab;
      m_hitInt[1][i] = chip;
      m_hitInt[2][i] = (*ints[1])[i];
      m_hitInt[3][i] = (*ints[2])[i];
      const auto pos = hit.getPosition();
      // kFloatNames order
      m_hitFloat[0][i] = (*floats[0])[i];
      m_hitFloat[1][i] = (*floats[1])[i];
      m_hitFloat[2][i] = hit.getEnergy();
      m_hitFloat[3][i] = pos.x;
      m_hitFloat[4][i] = pos.y;
      m_hitFloat[5][i] = pos.z;
      m_hitFloat[6][i] = (*floats[2])[i];
      m_hitFloat[7][i] = (*floats[3])[i];
      slabs.insert(slab);
      chips.insert((static_cast<long long>(slab) << 16) | chip);
      sumHg += (*floats[0])[i];
      sumE += hit.getEnergy();
    }
    m_nhit = static_cast<int>(n);
    m_nslab = static_cast<int>(slabs.size());
    m_nchip = static_cast<int>(chips.size());
    m_sumHg = static_cast<float>(sumHg);
    m_sumE = static_cast<float>(sumE);
    const std::size_t nScal = m_scalarNames.size(), nLay = m_layerNames.size() * m_nLayers.value();
    for (std::size_t b = 0; b <= m_prefixes.size(); ++b) {
      const std::size_t off = b == 0 ? 0 : nScal + nLay + (b - 1) * nScal;
      for (std::size_t i = 0; i < nScal; ++i) {
        m_scal[b * nScal + i] = par[off + i];
        if (m_scalarNames[i] == "is_shower") m_flag[b] = par[off + i] != 0;
      }
    }
    for (std::size_t i = 0; i < nLay; ++i) m_layers[i] = par[nScal + i];
    m_tree->Fill();
    return StatusCode::SUCCESS;
  }

  StatusCode finalize() override {
    if (m_file) {
      m_file->cd();
      m_tree->Write();
      const long long n = m_tree->GetEntries();
      m_file->Close();
      m_file.reset();
      if (std::rename((m_output.value() + ".tmp").c_str(), m_output.value().c_str()) != 0)
        return error() << "cannot rename to " << m_output.value() << endmsg, StatusCode::FAILURE;
      info() << "wrote " << n << " events to " << m_output.value() << endmsg;
    }
    return Gaudi::Algorithm::finalize();
  }

private:
  static constexpr std::size_t kMaxHits = 15 * 16 * 64;
  static constexpr int kNFloat = 8;
  static constexpr const char* kFloatNames[kNFloat] = {"hit_hg", "hit_lg", "hit_energy", "hit_x", "hit_y", "hit_z",
                                                       "hit_w_energy", "hit_X0"};
  static int idIndex(const std::string& n) { return n == "run" ? 0 : n == "event" ? 1 : n == "spill" ? 2 : 3; }
  // siwecal_validation._threshold_prefix: 0.5 -> mip05, 1.0 -> mip1
  static std::string prefix(double t) {
    char b[32];
    std::snprintf(b, sizeof b, "%.1f", t);
    std::string s(b);
    s.erase(std::remove(s.begin(), s.end(), '.'), s.end());
    while (!s.empty() && s.back() == '0') s.pop_back();
    return "mip" + s;
  }

  Gaudi::Property<std::string> m_output{this, "OutputFile", "", "valtree file"};
  Gaudi::Property<std::string> m_treeName{this, "TreeName", "ecal", "tree name"};
  Gaudi::Property<std::string> m_selection{this, "SelectionAlgorithm", "",
                                           "filter whose decision selects the events (empty: all events)"};
  Gaudi::Property<std::string> m_clusterName{this, "InputClusters", "ECalPid", "PID clusters"};
  Gaudi::Property<std::string> m_hitName{this, "InputCaloHits", "ECalHits", "hits"};
  Gaudi::Property<std::string> m_headerName{this, "InputEventHeader", "EventHeader", "event header"};
  Gaudi::Property<int> m_nLayers{this, "NLayers", 15, "layers of the per-layer blocks (EcalShowerVariables NLayers)"};
  Gaudi::Property<std::vector<double>> m_mipThresholds{this, "MipThresholds", {},
                                                       "the MIP-variant blocks (EcalShowerVariables MipThresholds)"};

  std::unique_ptr<k4FWCore::DataHandle<edm4hep::ClusterCollection>> m_clusters;
  std::unique_ptr<k4FWCore::DataHandle<edm4hep::CalorimeterHitCollection>> m_hits;
  std::unique_ptr<k4FWCore::DataHandle<edm4hep::EventHeaderCollection>> m_header;
  std::vector<std::pair<std::string, std::unique_ptr<k4FWCore::DataHandle<podio::UserDataCollection<std::int32_t>>>>> m_ints;
  std::vector<std::pair<std::string, std::unique_ptr<k4FWCore::DataHandle<podio::UserDataCollection<float>>>>> m_floats;
  std::vector<std::string> m_scalarNames, m_layerNames, m_prefixes;
  std::size_t m_width = 0;
  std::unique_ptr<TFile> m_file;
  TTree* m_tree = nullptr;
  // branch buffers (the job is sequential; execute is const only by the Gaudi signature)
  mutable int m_id[4] = {0, 0, 0, 0};
  mutable int m_nhit = 0, m_nslab = 0, m_nchip = 0;
  mutable float m_sumHg = 0, m_sumE = 0;
  mutable std::vector<std::vector<int>> m_hitInt;
  mutable std::vector<std::vector<float>> m_hitFloat;
  mutable std::vector<double> m_scal, m_layers;
  mutable std::vector<char> m_flag;
};

DECLARE_COMPONENT(EcalValTreeWriter)
