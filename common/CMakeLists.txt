# common/: headers (interface target siwecal_common), mappings and Python helpers; nothing to compile but tests.
install(DIRECTORY mappings/ DESTINATION ${SIWECAL_SHARE_DIR}/mappings)
if(BUILD_TESTING)
  add_executable(test_data_path tests/test_data_path.cpp)
  target_link_libraries(test_data_path PRIVATE siwecal_common)
  add_test(NAME data_path COMMAND test_data_path ${PROJECT_SOURCE_DIR})
endif()
