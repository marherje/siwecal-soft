# reconstruction/: algorithms shared by the data and the simulation chains.
#   SiWEcalPID       shower variables, event selection (EcalEventSelection) and the valtree (EcalValTreeWriter):
#                    one Gaudi job, options pid/options/run_pid.py, driver jobs/run_pid_batch.py
#   SiWEcalTracking  ACTS geometry service, shower tagger, measurement converter, proto-tracker (data + Sim* variants)
gaudi_add_module(SiWEcalPID
  SOURCES pid/src/EcalShowerVariables.cpp pid/src/EcalEventSelection.cpp pid/src/EcalValTreeWriter.cpp
  LINK Gaudi::GaudiKernel k4FWCore::k4FWCore EDM4HEP::edm4hep podio::podio podio::podioRootIO
       ROOT::Core ROOT::RIO ROOT::Tree DD4hep::DDCore siwecal_common)
target_include_directories(SiWEcalPID PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/pid/include)

gaudi_add_module(SiWEcalTracking
  SOURCES tracking/src/ACTSGeoSvc.cpp tracking/src/ShowerTagger.cpp tracking/src/SiPadMeasConverter.cpp
          tracking/src/ACTSProtoTracker.cpp
  LINK Gaudi::GaudiKernel k4FWCore::k4FWCore EDM4HEP::edm4hep podio::podio podio::podioRootIO
       DD4hep::DDCore DD4hep::DDRec ROOT::Core Acts::Core Acts::PluginDD4hep k4ActsTracking::k4ActsTracking
       siwecal_common siwecal_acts_includes)
target_include_directories(SiWEcalTracking PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/tracking/include)

install(DIRECTORY pid/options/ tracking/options/ DESTINATION ${SIWECAL_SHARE_DIR}/options FILES_MATCHING PATTERN "*.py")
