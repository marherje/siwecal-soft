#include "siwecal/ACTSGeoSvc.h"
#include "siwecal/PadMapGeometry.h"
#include "siwecal/DataPath.h"
#include "siwecal/SiPadLayerGeometry.h"
#include "DD4hep/Detector.h"
#include "Acts/Definitions/Algebra.hpp"
#include "Acts/Definitions/Units.hpp"
#include "Acts/Geometry/GeometryContext.hpp"
#include "Acts/Geometry/GeometryIdentifier.hpp"
#include "Acts/Geometry/Layer.hpp"
#include "Acts/Geometry/LayerArrayCreator.hpp"
#include "Acts/Geometry/PlaneLayer.hpp"
#include "Acts/Geometry/TrackingGeometry.hpp"
#include "Acts/Geometry/TrackingVolume.hpp"
#include "Acts/Geometry/TrackingVolumeArrayCreator.hpp"
#include "Acts/Geometry/CuboidVolumeBounds.hpp"
#include "Acts/Surfaces/RectangleBounds.hpp"
#include "Acts/Surfaces/PlaneSurface.hpp"
#include "Acts/Surfaces/PlanarBounds.hpp"
#include "Acts/Surfaces/Surface.hpp"
#include "Acts/Surfaces/SurfaceArray.hpp"
#include "Acts/Utilities/AxisDefinitions.hpp"
#include "Acts/Utilities/BinningData.hpp"
#include "Acts/Utilities/Logger.hpp"
#include "Acts/Material/Material.hpp"
#include "Acts/Material/MaterialSlab.hpp"
#include "Acts/Material/HomogeneousSurfaceMaterial.hpp"
#include <algorithm>
#include <cmath>
#include <string>

// ---------------------------------------------------------------------------
// SNDDetectorElement
// A minimal DetectorElementBase so the CKF actor classifies each plane as
// sensitive (CKF checks associatedDetectorElement() != nullptr at line 442
// of CombinatorialKalmanFilter.hpp; without this, every surface is "passive").
// ---------------------------------------------------------------------------

class SNDDetectorElement : public Acts::DetectorElementBase {
public:
  SNDDetectorElement(std::shared_ptr<const Acts::PlanarBounds> bounds,
                     Acts::Transform3 transform, double thickness)
      : m_transform(std::move(transform)), m_thickness(thickness) {
    // PlaneSurface(bounds, detElement) sets m_associatedDetectorElement = this
    m_surface = Acts::Surface::makeShared<Acts::PlaneSurface>(bounds, *this);
  }

  const Acts::Transform3& transform(const Acts::GeometryContext&) const override {
    return m_transform;
  }
  const Acts::Surface& surface() const override { return *m_surface; }
  Acts::Surface&       surface() override       { return *m_surface; }
  double thickness() const override { return m_thickness; }

private:
  Acts::Transform3 m_transform;
  double m_thickness;
  std::shared_ptr<Acts::PlaneSurface> m_surface;
};

namespace {
// Tungsten material constants, consistent with
// siwecal/PadMapGeometry.h's kWX0Mm (3.5 mm radiation length) -- the
// same constant EcalEventBuilder uses for hit_X0. L0/A/Z/rho are the PDG
// values for W; L0 only affects hadronic-interaction bookkeeping, not the
// Highland multiple-scattering estimate the CKF actually uses (that one only
// reads X0), so approximate precision there is fine.
constexpr float kWL0Mm  = 99.4f;   // nuclear interaction length [mm]
constexpr float kWA     = 183.84f;
constexpr float kWZ     = 74.0f;
constexpr float kWRhoG  = 19.3f;   // g/cm^3

Acts::MaterialSlab makeTungstenSlab(double thicknessMm) {
  return Acts::MaterialSlab(
      Acts::Material::fromMassDensity(
          static_cast<float>(k4siwecal::kWX0Mm), kWL0Mm, kWA, kWZ, kWRhoG),
      static_cast<float>(thicknessMm));
}

// Query DD4hep for radiation length and nuclear interaction length of a
// named material, then pack into an Acts::MaterialSlab of the given thickness.
// DD4hep radLength()/intLength() return cm; ACTS wants mm.
Acts::MaterialSlab makeSlab(const std::string& matName, double thicknessMm) {
    auto& desc = dd4hep::Detector::getInstance();
    dd4hep::Material mat = desc.material(matName);
    float X0  = static_cast<float>(mat.radLength() * 10.0);   // cm → mm
    float L0  = static_cast<float>(mat.intLength() * 10.0);   // cm → mm
    float rho = static_cast<float>(mat.density());             // g/cm³
    float A   = static_cast<float>(mat.A());
    float Z   = static_cast<float>(mat.Z());
    return Acts::MaterialSlab(
        Acts::Material::fromMassDensity(X0, L0, A, Z, rho),
        static_cast<float>(thicknessMm));
}
} // namespace

ACTSGeoSvc::ACTSGeoSvc(const std::string& name, ISvcLocator* svcLoc)
    : extends(name, svcLoc) {}

// ---------------------------------------------------------------------------
// Planes from the DD4hep compact (simulation): the shared DetElement walk of SiPadLayerGeometry.h (DetectorFlipper
// reads the same helper, so the two cannot disagree about where layer N sits); each layer's slice stack, without
// air/vacuum, is folded into one homogeneous slab.
// ---------------------------------------------------------------------------
StatusCode ACTSGeoSvc::planesFromDD4hep(std::vector<PlaneInfo>& planes) {
  const std::string compact = siwecal::resolveDataPath(m_compactFile.value());
  auto& desc = dd4hep::Detector::getInstance();
  desc.fromXML(compact);
  info() << "[ACTSGeoSvc] DD4hep geometry loaded from: " << compact << endmsg;

  // Where the sensitive layers are comes from the shared DD4hep walk in
  // SiPadLayerGeometry.h, not from a copy of it here: DetectorFlipper reads the
  // same helper, so the two cannot disagree about where layer N sits. See that
  // header for why the tree is walked by DetElement rather than by volume name.
  const std::string detName = "SiPad";
  std::vector<sipad::LayerPlane> layerPlanes;
  try {
    layerPlanes = sipad::sensitiveLayers(desc, detName);
  } catch (const std::exception& e) {
    error() << "[ACTSGeoSvc] " << e.what() << endmsg;
    return StatusCode::FAILURE;
  }

  
  for (const auto& lp : layerPlanes) {
    PlaneInfo pi{};
    pi.z          = lp.z;
    pi.halfX      = lp.halfX;
    pi.halfY      = lp.halfY;
    pi.thickness  = lp.halfThickness;
    pi.plane      = -1;
    pi.detID      = 1;
    pi.station    = -1;
    pi.layerInDet = lp.layer;

    // Fold the layer's slice stack into one homogeneous slab attached to the
    // surface. The helper already dropped air/vacuum and resolved the tiled
    // sensitive slice down to the silicon.
    for (const auto& s : lp.slices) {
      const Acts::MaterialSlab slab = makeSlab(s.material, s.thicknessMm);
      pi.material = (pi.material.thickness() > 0.0)
                        ? Acts::MaterialSlab::combineLayers(pi.material, slab)
                        : slab;
    }

    planes.push_back(pi);
  }

  if (planes.empty()) {
    error() << "[ACTSGeoSvc] No sensitive planes found for detector: "
            << detName << endmsg;
    return StatusCode::FAILURE;
  }

  return StatusCode::SUCCESS;
}

// ---------------------------------------------------------------------------
// Planes from slab_z_positions.yml (data): per-slab z and W thickness, nominal plane thickness, configured envelope.
// ---------------------------------------------------------------------------
StatusCode ACTSGeoSvc::planesFromSlabZ(std::vector<PlaneInfo>& planes) {
  const std::string slabZFile = siwecal::resolveDataPath(m_slabZFile.value());
  k4siwecal::SlabGeometry slabGeo = k4siwecal::SlabGeometry::fromYamlFile(slabZFile);
  info() << "[ACTSGeoSvc] Slab geometry loaded from: " << slabZFile << endmsg;

  const double halfX = m_halfSizeX.value();
  const double halfY = m_halfSizeY.value();
  // Half-thickness placeholder [mm]: this repo has no per-slab Si/PCB/Cu
  // slice thicknesses to sum (unlike the simulation's DD4hep slice stack), so
  // the plane is given a thin nominal thickness -- what matters for the CKF
  // is the *surface material* (set below from the W budget), not this value.
  constexpr double kNominalHalfThicknessMm = 0.5;

  constexpr int kNumSlabs = 15;
  for (int slab = 0; slab < kNumSlabs; ++slab) {
    const double z = slabGeo.slabZ(slab);
    if (!std::isfinite(z)) {
      error() << "[ACTSGeoSvc] hit_slab " << slab
              << " has no z position in " << slabZFile << endmsg;
      return StatusCode::FAILURE;
    }
    PlaneInfo pi{};
    pi.z          = z;
    pi.halfX      = halfX;
    pi.halfY      = halfY;
    pi.thickness  = kNominalHalfThicknessMm;
    pi.plane      = -1;
    pi.detID      = 1;   // SiPad -- same address convention as siwecal_k4sim
    pi.station    = -1;
    pi.layerInDet = slab;
    // slabWOverX0() = w_thickness_mm[slab] / kWX0Mm, so the thickness this
    // slab's W absorber has is slabWOverX0() * kWX0Mm -- recovers the raw
    // mm value from the file without adding a new getter to PadMapGeometry.h.
    const double wThicknessMm = slabGeo.slabWOverX0(slab) * k4siwecal::kWX0Mm;
    pi.material = makeTungstenSlab(wThicknessMm);
    planes.push_back(pi);
  }

  return StatusCode::SUCCESS;
}

StatusCode ACTSGeoSvc::initialize() {
  StatusCode sc = Service::initialize();
  if (sc.isFailure()) return sc;

  std::string source = m_geometrySource.value();
  const bool hasCompact = !m_compactFile.value().empty(), hasSlabZ = !m_slabZFile.value().empty();
  if (source == "auto") {
    if (hasCompact == hasSlabZ) {
      error() << "[ACTSGeoSvc] GeometrySource=auto needs exactly one of CompactFile (simulation) and SlabZFile "
                 "(data); got " << (hasCompact ? "both" : "neither") << endmsg;
      return StatusCode::FAILURE;
    }
    source = hasCompact ? "dd4hep" : "slabz";
  }
  std::vector<PlaneInfo> allPlanes;
  try {
    if (source == "dd4hep") {
      if (!hasCompact) { error() << "[ACTSGeoSvc] GeometrySource=dd4hep needs CompactFile" << endmsg; return StatusCode::FAILURE; }
      sc = planesFromDD4hep(allPlanes);
    } else if (source == "slabz") {
      if (!hasSlabZ) { error() << "[ACTSGeoSvc] GeometrySource=slabz needs SlabZFile" << endmsg; return StatusCode::FAILURE; }
      sc = planesFromSlabZ(allPlanes);
    } else {
      error() << "[ACTSGeoSvc] unknown GeometrySource '" << source << "' (auto, dd4hep, slabz)" << endmsg;
      return StatusCode::FAILURE;
    }
  } catch (const std::exception& e) {
    error() << "[ACTSGeoSvc] " << e.what() << endmsg;
    return StatusCode::FAILURE;
  }
  if (sc.isFailure()) return sc;
  if (allPlanes.empty()) {
    error() << "[ACTSGeoSvc] no sensitive planes (" << source << ")" << endmsg;
    return StatusCode::FAILURE;
  }

  std::sort(allPlanes.begin(), allPlanes.end(),
            [](const PlaneInfo& a, const PlaneInfo& b) { return a.z < b.z; });
  double halfX = 0.0, halfY = 0.0;   // envelope of the navigation layers and the volume
  for (const auto& pi : allPlanes) {
    halfX = std::max(halfX, pi.halfX);
    halfY = std::max(halfY, pi.halfY);
  }

  info() << "[ACTSGeoSvc] " << allPlanes.size() << " SiPad planes from " << source << ":" << endmsg;
  for (const auto& pi : allPlanes) {
    info() << "[ACTSGeoSvc]   slab=" << pi.layerInDet
           << " z=" << pi.z
           << " halfX=" << pi.halfX << " halfY=" << pi.halfY
           << " thickness=" << pi.thickness
           << " | material t=" << pi.material.thickness()
           << " mm X0=" << pi.material.material().X0()
           << " mm t/X0=" << pi.material.thicknessInX0() << endmsg;
  }

  // =========================================================================
  // Build TrackingGeometry using PlaneLayer directly (same scaffolding as
  // the simulation's ACTSGeoSvc: avoids CuboidVolumeBuilder's position offset
  // bug). Each plane becomes a PlaneSurface + PlaneLayer with absolute
  // position; all layers sit in one CuboidVolumeBounds TrackingVolume.
  // =========================================================================

  std::vector<Acts::LayerPtr> allLayers;
  allLayers.reserve(allPlanes.size());

  // Rotation 90 deg around Y: maps local Z (surface normal) to global X, so
  // tracks run along ACTS X and avoid the theta=0 bound-coordinate
  // singularity. Same convention as siwecal_k4sim -- local x maps to minus
  // global Z, see docs/data/acts_integration.md's coordinate section.
  Acts::RotationMatrix3 rot90Y =
      Eigen::AngleAxisd(M_PI / 2.0,
                        Acts::Vector3::UnitY()).toRotationMatrix();

  for (std::size_t i = 0; i < allPlanes.size(); ++i) {
    const auto& pi = allPlanes[i];

    Acts::Transform3 transform = Acts::Transform3::Identity();
    transform.rotate(rot90Y);
    transform.pretranslate(Acts::Vector3(pi.z, 0.0, 0.0));

    auto bounds = std::make_shared<Acts::RectangleBounds>(pi.halfX, pi.halfY);
    const double layerThickness = 2.0 * pi.thickness + 0.01;

    auto detElem = std::make_shared<SNDDetectorElement>(bounds, transform, pi.thickness);
    m_detectorElements.push_back(detElem);

    auto surfaceArray = std::make_unique<Acts::SurfaceArray>(
        detElem->surface().getSharedPtr());

    auto layer = Acts::PlaneLayer::create(
        transform, bounds, std::move(surfaceArray), layerThickness,
        nullptr, Acts::active);

    if (pi.material.thickness() > 0.0) {
      auto surfMat = std::make_shared<Acts::HomogeneousSurfaceMaterial>(pi.material);
      detElem->surface().assignSurfaceMaterial(surfMat);
    } else {
      warning() << "[ACTSGeoSvc] hit_slab " << pi.layerInDet
                << " has no material budget -- surface left material-free."
                << endmsg;
    }

    allLayers.push_back(layer);
  }

  // ---- Navigation layers at the beam-Z extremes -----------------------
  const double zMin = allPlanes.front().z - allPlanes.front().thickness - 5.0;
  const double zMax = allPlanes.back().z  + allPlanes.back().thickness  + 5.0;

  {
    Acts::Transform3 t = Acts::Transform3::Identity();
    t.rotate(rot90Y);
    t.pretranslate(Acts::Vector3(zMin, 0.0, 0.0));
    auto navBounds = std::make_shared<Acts::RectangleBounds>(halfX + 5.0, halfY + 5.0);
    auto navLayer = Acts::PlaneLayer::create(t, navBounds, nullptr, 0.0, nullptr, Acts::navigation);
    allLayers.insert(allLayers.begin(), navLayer);
  }
  {
    Acts::Transform3 t = Acts::Transform3::Identity();
    t.rotate(rot90Y);
    t.pretranslate(Acts::Vector3(zMax, 0.0, 0.0));
    auto navBounds = std::make_shared<Acts::RectangleBounds>(halfX + 5.0, halfY + 5.0);
    auto navLayer = Acts::PlaneLayer::create(t, navBounds, nullptr, 0.0, nullptr, Acts::navigation);
    allLayers.push_back(navLayer);
  }

  // ---- LayerArray, binned along X (beam axis) --------------------------
  Acts::LayerArrayCreator::Config lacCfg{};
  Acts::LayerArrayCreator lac(
      lacCfg, Acts::getDefaultLogger("LayerArrayCreator", Acts::Logging::WARNING));

  auto layerArray = lac.layerArray(
      m_gctx, allLayers, zMin - 1.0, zMax + 1.0,
      Acts::arbitrary, Acts::AxisDirection::AxisX);

  // ---- TrackingVolume ----------------------------------------------------
  const double volumeHalfZ = halfX + 15.0;
  const double volumeHalfY = halfY + 15.0;
  const double volumeHalfX = std::max(std::abs(zMin), std::abs(zMax)) + 2.0;

  auto volumeBounds = std::make_shared<Acts::CuboidVolumeBounds>(
      volumeHalfX, volumeHalfY, volumeHalfZ);

  Acts::Transform3 volumeTransform = Acts::Transform3::Identity();

  auto trackingVolume = std::make_shared<Acts::TrackingVolume>(
    volumeTransform, volumeBounds, nullptr, std::move(layerArray),
    nullptr, Acts::MutableTrackingVolumeVector{}, "SNDVolume");

  // ---- TrackingGeometry ----------------------------------------------------
  Acts::GeometryIdentifierHook hook{};
  m_trackingGeometry = std::make_shared<Acts::TrackingGeometry>(
    trackingVolume, nullptr, hook, Acts::getDummyLogger());

  if (!m_trackingGeometry) {
    error() << "[ACTSGeoSvc] Failed to build ACTS TrackingGeometry." << endmsg;
    return StatusCode::FAILURE;
  }
  info() << "[ACTSGeoSvc] TrackingGeometry built with PlaneLayer." << endmsg;

  // Collect sensitive surfaces from confined layers -- same idiom as
  // siwecal_k4sim: use the module surfaces stored in each layer's
  // SurfaceArray (the ones the Navigator actually visits), not
  // surfaceRepresentation() (that would give the layer envelope's geoID).
  const Acts::TrackingVolume* world = m_trackingGeometry->highestTrackingVolume();
  if (world && world->confinedLayers()) {
    for (const auto& layer : world->confinedLayers()->arrayObjects()) {
      if (layer && layer->layerType() == Acts::active) {
        const Acts::SurfaceArray* sa = layer->surfaceArray();
        if (sa) {
          for (const Acts::Surface* sf : sa->surfaces()) {
            if (sf) m_allSurfaces.push_back(sf);
          }
        } else {
          m_allSurfaces.push_back(&layer->surfaceRepresentation());
        }
      }
    }
  }
  std::sort(m_allSurfaces.begin(), m_allSurfaces.end(),
            [&](const Acts::Surface* a, const Acts::Surface* b) {
              return a->center(m_gctx).x() < b->center(m_gctx).x();
            });

  if (allPlanes.size() == m_allSurfaces.size()) {
    for (std::size_t i = 0; i < allPlanes.size(); ++i) {
      const auto& pi = allPlanes[i];
      m_surfaceByAddressMap[{pi.detID, pi.station, pi.layerInDet, pi.plane}]
          = m_allSurfaces[i];
    }
  } else {
    warning() << "[ACTSGeoSvc] allPlanes.size()=" << allPlanes.size()
              << " != m_allSurfaces.size()=" << m_allSurfaces.size()
              << " -- surfaceByAddress map not populated." << endmsg;
  }

  info() << "[ACTSGeoSvc] TrackingGeometry built. Total surfaces: "
         << m_allSurfaces.size() << endmsg;

  return StatusCode::SUCCESS;
}

// ---------------------------------------------------------------------------
// finalize()
// ---------------------------------------------------------------------------

StatusCode ACTSGeoSvc::finalize() {
  return Service::finalize();
}

// ---------------------------------------------------------------------------
// Interface method implementations
// ---------------------------------------------------------------------------

const Acts::TrackingGeometry& ACTSGeoSvc::trackingGeometry() const {
  return *m_trackingGeometry;
}

const std::vector<const Acts::Surface*>& ACTSGeoSvc::allSurfaces() const {
  return m_allSurfaces;
}

const Acts::Surface* ACTSGeoSvc::surfaceByAddress(
    int detID, int station, int layer, int plane) const {
  auto it = m_surfaceByAddressMap.find({detID, station, layer, plane});
  return (it != m_surfaceByAddressMap.end()) ? it->second : nullptr;
}

const Acts::GeometryContext& ACTSGeoSvc::geometryContext() const {
  return m_gctx;
}

DECLARE_COMPONENT(ACTSGeoSvc)
