# siwecal-soft -- SiW-ECAL software: data conversion, simulation, common reconstruction, analysis.
# One project, one install prefix: source init_siwecalsoft.sh, then ./build.sh (or the cmake lines in it).
cmake_minimum_required(VERSION 3.20)
project(SiWEcalSoft VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)
  set(CMAKE_INSTALL_PREFIX "${PROJECT_SOURCE_DIR}/install" CACHE PATH "install prefix" FORCE)
endif()

include(GNUInstallDirs)
include(CTest)

find_package(Gaudi REQUIRED)
find_package(k4FWCore REQUIRED)
find_package(EDM4HEP REQUIRED)
find_package(podio REQUIRED)
find_package(DD4hep REQUIRED COMPONENTS DDCore DDRec DDG4)
find_package(ROOT REQUIRED COMPONENTS Core RIO Tree TreePlayer Hist Spectrum ROOTNTuple MathCore Minuit2)
find_package(LCIO REQUIRED)               # EcalLcioDecoder (EUDAQ .slcio)
find_package(Acts 44.3.0 REQUIRED COMPONENTS Core PluginDD4hep)
find_package(k4ActsTracking REQUIRED)

# Every Gaudi component name is defined exactly once: two libraries declaring the same component make
# 'from Configurables import X' ambiguous. Fails the configure step otherwise.
include(cmake/CheckUniqueComponents.cmake)
siwecal_check_unique_components()

# Header-only interface shared by all areas: common/include/siwecal (pad maps, slab geometry, calib tables, DataPath)
add_library(siwecal_common INTERFACE)
target_include_directories(siwecal_common INTERFACE ${PROJECT_SOURCE_DIR}/common/include)
# ACTS headers from the Acts::Core target (the hashed include dir changes with the key4hep release)
get_target_property(_acts_include_dirs Acts::Core INTERFACE_INCLUDE_DIRECTORIES)
add_library(siwecal_acts_includes INTERFACE)
if(_acts_include_dirs)
  target_include_directories(siwecal_acts_includes INTERFACE ${_acts_include_dirs})
endif()

set(SIWECAL_SHARE_DIR "${CMAKE_INSTALL_DATADIR}/SiWEcalSoft")
# Installed plugin libraries find their dependencies without LD_LIBRARY_PATH gymnastics
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)

add_subdirectory(common)
add_subdirectory(reconstruction)
add_subdirectory(data_conversion)
add_subdirectory(simulation)
