#pragma once

#include "siwecal/ISNDGeoSvc.h"
#include "GaudiKernel/Service.h"
#include "Acts/Geometry/GeometryContext.hpp"
#include "Acts/Geometry/TrackingGeometry.hpp"
#include "Acts/MagneticField/MagneticFieldContext.hpp"
#include "Acts/Geometry/DetectorElementBase.hpp"
#include "Acts/Material/MaterialSlab.hpp"
#include "Acts/Surfaces/Surface.hpp"
#include <map>
#include <memory>
#include <string>
#include <tuple>
#include <vector>

// ACTSGeoSvc -- the 15 SiPad plane surfaces of the SiW-ECAL as an ACTS TrackingGeometry, shared by the data and the
// simulation chains. Address convention: detID=1 "SiPad", station=-1, layer = slab 0..14, plane=-1; surfaces are
// rotated 90 deg around Y so tracks run along ACTS X (no theta=0 singularity, docs/data/acts_integration.md).
//
// Two sources for the planes, same scaffolding after that:
//   GeometrySource="dd4hep"  CompactFile: walk the DD4hep DetElement tree (simulation; the full slice stack of each
//                            layer -- W, Si, PCB, Cu, CF -- becomes the surface material).
//   GeometrySource="slabz"   SlabZFile: common/mappings/slab_z_positions.yml (data; W absorber only, nominal
//                            thickness, HalfSizeX/Y envelope).
//   GeometrySource="auto"    (default) whichever of CompactFile / SlabZFile is set; both or neither is an error.
// Relative file names are resolved with siwecal::resolveDataPath (mappings, repo root, working directory).
class ACTSGeoSvc : public extends<Service, ISNDGeoSvc> {
public:
  ACTSGeoSvc(const std::string& name, ISvcLocator* svcLoc);

  StatusCode initialize() override;
  StatusCode finalize()   override;

  // IActsGeoSvc interface
  const Acts::TrackingGeometry& trackingGeometry() const override;

  // ISNDGeoSvc extensions
  const std::vector<const Acts::Surface*>& allSurfaces() const override;
  const Acts::GeometryContext& geometryContext() const override;
  const Acts::Surface* surfaceByAddress(
      int detID, int station, int layer, int plane) const override;

  // One sensitive plane, before it becomes an ACTS surface.
  struct PlaneInfo {
    double z;           // global Z centre [mm] (beam axis, before rot90Y)
    double halfX;       // transverse half-size in X [mm]
    double halfY;       // transverse half-size in Y [mm]
    double thickness;   // half-thickness in Z [mm]
    int    plane;       // -1 = pixel (SiPad)
    int    detID;       // 1 = SiPad
    int    station;     // -1 (SiPad has no stations)
    int    layerInDet;  // slab index 0..14
    Acts::MaterialSlab material;
  };

private:
  StatusCode planesFromDD4hep(std::vector<PlaneInfo>& planes);
  StatusCode planesFromSlabZ(std::vector<PlaneInfo>& planes);

  Gaudi::Property<std::string> m_geometrySource{
      this, "GeometrySource", "auto",
      "Where the planes come from: 'dd4hep' (CompactFile), 'slabz' (SlabZFile) or 'auto' (the one that is set)."};

  Gaudi::Property<std::string> m_compactFile{
      this, "CompactFile", "",
      "DD4hep compact XML (simulation/geometry/...): planes and their full material stack from the DetElement tree."};

  Gaudi::Property<std::string> m_slabZFile{
      this, "SlabZFile", "",
      "slab_z_positions.yml (common/mappings): per-slab z and W thickness, for data without a DD4hep description."};

  Gaudi::Property<double> m_padPitchMm{
      this, "PadPitchMm", 5.53,
      "Pad pitch [mm] (slabz mode; informational, the measurement variance is set in SiPadMeasConverter)."};

  Gaudi::Property<double> m_halfSizeX{
      this, "HalfSizeX", 90.0,
      "Transverse half-size in X [mm] of each plane surface (slabz mode)."};

  Gaudi::Property<double> m_halfSizeY{
      this, "HalfSizeY", 90.0,
      "Transverse half-size in Y [mm] of each plane surface (slabz mode)."};

  std::shared_ptr<const Acts::TrackingGeometry> m_trackingGeometry;
  std::vector<const Acts::Surface*>             m_allSurfaces;
  Acts::GeometryContext                         m_gctx;
  // Detector elements must outlive all surfaces (surfaces hold raw pointers back).
  std::vector<std::shared_ptr<Acts::DetectorElementBase>> m_detectorElements;

  // key = (detID, station, layerInDet, plane)
  std::map<std::tuple<int,int,int,int>, const Acts::Surface*> m_surfaceByAddressMap;
};
