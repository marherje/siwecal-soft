# simulation/: DD4hep detector plugin and the digitisation chain (ddsim output -> data-like ecal tree).
dd4hep_add_plugin(SiPadDetector_plugin SOURCES detector/SiPadDetector.cpp)
target_link_libraries(SiPadDetector_plugin DD4hep::DDCore)

gaudi_add_module(SiWEcalSimDigi
  SOURCES digitisation/src/GeV2MIPConversion.cpp digitisation/src/BasicDigitizer.cpp
          digitisation/src/ContributionInspector.cpp digitisation/src/EventWindowSplitter.cpp
          digitisation/src/EventShuffler.cpp digitisation/src/EDM4HEP2RNTuple.cpp digitisation/src/MIPExtractor.cpp
          digitisation/src/RealDigitizer.cpp digitisation/src/DetectorFlipper.cpp digitisation/src/ChannelMapper.cpp
          digitisation/src/AdcDigitizer.cpp digitisation/src/EcalTreeWriter.cpp
  LINK Gaudi::GaudiKernel k4FWCore::k4FWCore EDM4HEP::edm4hep podio::podio podio::podioRootIO
       DD4hep::DDCore DD4hep::DDRec ROOT::ROOTNTuple ROOT::Hist ROOT::Tree siwecal_common)

install(TARGETS SiPadDetector_plugin LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(DIRECTORY geometry/ DESTINATION ${SIWECAL_SHARE_DIR}/geometry FILES_MATCHING PATTERN "*.xml")
