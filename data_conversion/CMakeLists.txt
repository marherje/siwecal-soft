# data_conversion/: raw/LCIO decoding, event building, calibration producers, ecal tree -> EDM4hep.
gaudi_add_module(SiWEcalDataConversion
  SOURCES src/EcalRawDecoder.cpp src/EcalLcioDecoder.cpp src/EcalEventBuilder.cpp src/EcalToEDM4hep.cpp
          src/PedestalMipCalibrator.cpp src/GainAnchorCalibrator.cpp src/OccupancySagCalibrator.cpp
          src/TriggerTurnOnCalibrator.cpp
  LINK Gaudi::GaudiKernel k4FWCore::k4FWCore EDM4HEP::edm4hep podio::podio podio::podioRootIO
       ROOT::Core ROOT::RIO ROOT::Tree ROOT::TreePlayer ROOT::Spectrum ROOT::MathCore ROOT::Minuit2
       DD4hep::DDCore LCIO::lcio siwecal_common)
target_include_directories(SiWEcalDataConversion PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
install(DIRECTORY options/ DESTINATION ${SIWECAL_SHARE_DIR}/options FILES_MATCHING PATTERN "*.py")

if(BUILD_TESTING)
  add_executable(test_gain_anchor_fit tests/test_gain_anchor_fit.cpp)
  target_include_directories(test_gain_anchor_fit PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
  add_test(NAME gain_anchor_fit COMMAND test_gain_anchor_fit)
endif()
