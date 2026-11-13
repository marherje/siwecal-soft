// resolveDataPath: absolute paths pass through, relative ones are found under SIWECAL_MAPPINGS then
// SIWECAL_SOFT_ROOT then the working directory, and a missing file throws with the places tried.
#include "siwecal/DataPath.h"
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>

static int fails = 0;
#define CHECK(c) do { if (!(c)) { std::cerr << "FAIL line " << __LINE__ << ": " #c "\n"; ++fails; } } while (0)

int main(int argc, char** argv) {
  if (argc < 2) { std::cerr << "usage: test_data_path <repo root>\n"; return 2; }
  const std::string root = argv[1];
  const std::string pad = "fev10_rotate_chip_channel_x_y_mapping.txt";
  ::unsetenv("SIWECAL_MAPPINGS");
  ::setenv("SIWECAL_SOFT_ROOT", root.c_str(), 1);
  CHECK(siwecal::resolveDataPath("common/mappings/" + pad) == root + "/common/mappings/" + pad);
  ::setenv("SIWECAL_MAPPINGS", (root + "/common/mappings").c_str(), 1);
  CHECK(siwecal::resolveDataPath(pad) == root + "/common/mappings/" + pad);
  CHECK(siwecal::resolveDataPath("/etc/hostname") == "/etc/hostname");
  bool threw = false;
  try { siwecal::resolveDataPath("no_such_table.txt"); } catch (const std::runtime_error& e) {
    threw = std::string(e.what()).find("no_such_table.txt") != std::string::npos;
  }
  CHECK(threw);
  std::cout << (fails ? "FAILED" : "OK") << "\n";
  return fails ? 1 : 0;
}
