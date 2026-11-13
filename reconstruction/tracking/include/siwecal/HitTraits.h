#pragma once
// HitTraits -- what the tracking front-end (ShowerTagger, SiPadMeasConverter) needs to know about its input hits, so
// one source serves the data chain (edm4hep::CalorimeterHit, EcalToEDM4hep's ECalHits, cellID field 'slab') and the
// simulation chain (edm4hep::SimCalorimeterHit, the digitised SiPad hits, DD4hep cellID field 'layer').
// The data instantiation keeps the historical component names (ShowerTagger, SiPadMeasConverter); the simulation
// one is SimShowerTagger / SimSiPadMeasConverter (docs/tracking_unification.md).
#include "edm4hep/CalorimeterHitCollection.h"
#include "edm4hep/SimCalorimeterHitCollection.h"

namespace siwecal {

template <class HitCollection> struct HitTraits;

template <> struct HitTraits<edm4hep::CalorimeterHitCollection> {
  static constexpr const char* defaultInput = "ECalHits";
  static constexpr const char* defaultBitField = "system:8,slab:8,chip:16,channel:8,sca:8";  // EcalToEDM4hep
  static constexpr const char* defaultLayerField = "slab";
  static float time(const edm4hep::CalorimeterHit& h) { return h.getTime(); }
};

template <> struct HitTraits<edm4hep::SimCalorimeterHitCollection> {
  static constexpr const char* defaultInput = "SiPadHitsDigi";
  static constexpr const char* defaultBitField = "";   // the DD4hep readout's, set in the steering
  static constexpr const char* defaultLayerField = "layer";
  // MC truth: the time of the first contribution (a SimCalorimeterHit has no time of its own)
  static float time(const edm4hep::SimCalorimeterHit& h) {
    return h.contributions_size() > 0 ? static_cast<float>(h.getContributions(0).getTime()) : 0.0f;
  }
};

}  // namespace siwecal
