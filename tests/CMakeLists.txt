# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) 2026, Anne Skydancer (neo-j2k)
# The package smoke test, built against the staged package (verify_package.py gives -DSTAGE=...).
cmake_minimum_required(VERSION 3.25)
project(neoj2k_package_smoke LANGUAGES C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
find_library(NEOJ2K_LIB NAMES neoj2k PATHS "${STAGE}/lib/release" REQUIRED NO_DEFAULT_PATH)
add_executable(smoke smoke.c)
target_include_directories(smoke PRIVATE "${STAGE}/include")
target_link_libraries(smoke PRIVATE ${NEOJ2K_LIB})
if(NOT WIN32)
  set_target_properties(smoke PROPERTIES BUILD_RPATH "${STAGE}/lib/release")
endif()
