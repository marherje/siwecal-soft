#pragma once
// resolveDataPath -- one rule for every data file a Gaudi component opens (pad maps, slab_z_positions.yml,
// occupancy sag maps, compact XML...), so a job behaves the same from any working directory.
//
//   absolute path                      used as is
//   relative path, first that exists:  $SIWECAL_MAPPINGS/<p>   (common/mappings, exported by init_siwecalsoft.sh)
//                                      $SIWECAL_SOFT_ROOT/<p>  (repo root: 'common/mappings/x', 'simulation/geometry/y')
//                                      ./<p>                   (working directory, the historical behaviour)
//
// Nothing found throws std::runtime_error listing every place tried, instead of a component silently reading an
// empty table. Header-only, no Gaudi dependency (unit-tested in common/tests/test_data_path.cpp).
#include <cstdlib>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

namespace siwecal {

inline std::vector<std::string> dataPathCandidates(const std::string& p) {
  namespace fs = std::filesystem;
  if (p.empty() || fs::path(p).is_absolute()) return {p};
  std::vector<std::string> out;
  for (const char* var : {"SIWECAL_MAPPINGS", "SIWECAL_SOFT_ROOT"}) {
    if (const char* base = std::getenv(var); base && *base) out.push_back((fs::path(base) / p).string());
  }
  out.push_back(p);
  return out;
}

inline std::string resolveDataPath(const std::string& p) {
  namespace fs = std::filesystem;
  if (p.empty()) throw std::runtime_error("resolveDataPath: empty file name");
  const auto cands = dataPathCandidates(p);
  for (const auto& c : cands) {
    std::error_code ec;
    if (fs::exists(c, ec)) return c;
  }
  std::string msg = "resolveDataPath: '" + p + "' not found; tried:";
  for (const auto& c : cands) msg += " " + c;
  msg += " (source init_siwecalsoft.sh?)";
  throw std::runtime_error(msg);
}

}  // namespace siwecal
