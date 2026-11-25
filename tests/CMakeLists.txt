# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) 2026, Anne Skydancer (neo-j2k)
# The package smoke test, built against the staged package (verify_package.py gives -DSTAGE=...).
cmake_minimum_required(VERSION 3.25)
project(neoj2k_package_smoke LANGUAGES C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreadedDLL")
# The package is static-only: link neoj2k_static.lib / libneoj2k.a with NJ2K_STATIC defined.
find_library(NEOJ2K_LIB NAMES neoj2k_static libneoj2k.a PATHS "${STAGE}/lib/release" REQUIRED NO_DEFAULT_PATH)
add_executable(smoke smoke.c)
target_include_directories(smoke PRIVATE "${STAGE}/include")
target_compile_definitions(smoke PRIVATE NJ2K_STATIC EXPECT_VERSION="${EXPECT_VERSION}")
target_link_libraries(smoke PRIVATE ${NEOJ2K_LIB})
