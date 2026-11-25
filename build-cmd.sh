#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) 2026, Anne Skydancer (neo-j2k)
#
# Builds the neo-j2k static library (neoj2k_static.lib on Windows, libneoj2k.a on Linux) from the pinned submodule
# and lays out the autobuild package. The package is static-only: no shared library, no import library, and the
# OpenJPEG-compatible shim (the openjp2 module) is off; that shim and the shared library are distributed from the
# neo-j2k repository itself. Callers use the nj2k_* API only.
#   include/neoj2k/        neoj2k.h and neoj2k.hpp (the OpenJPEG-name headers neoj2k_openjpeg.h and compat/ are dropped)
#   lib/release/           neoj2k_static.lib (Windows) or libneoj2k.a (Linux)
#   LICENSES/              neo-j2k's licence, OpenJPEG's (the notices of the code neo-j2k ports), NOTICE.md
# The CMake package config (neoj2kConfig*.cmake, which with the shared library off exports the static target only) and
# neoj2k.pc (only generated for a shared build) are not staged: the install tree's config points at lib/neoj2k_static.lib
# and include/, while this package keeps the library in lib/release/, so a shipped config would be wrong; the package is
# consumed through autobuild, not find_package.
# Options: AVX2, no OpenSim profile, position-independent on Linux (the library's CMake always sets it, so the archive
# also links into a shared object) and the DLL C runtime (/MD) on Windows, as the viewer builds with; no link-time
# code generation (so any compiler version links it) and no dependencies beyond libc and libm.
# Consumers define NJ2K_STATIC when they compile against it.

cd "$(dirname "$0")"

# turn on verbose debugging output for parabuild logs.
exec 4>&1; export BASH_XTRACEFD=4; set -x
# make errors fatal
set -e
# complain about unset env variables
set -u

# The source: the pinned submodule; NEOJ2K_SOURCE_DIR points a local run at another checkout.
SOURCE_DIR="$(cd "${NEOJ2K_SOURCE_DIR:-neo-j2k}" && pwd)"

if [ -z "$AUTOBUILD" ] ; then
    exit 1
fi

if [[ "$OSTYPE" == "cygwin" || "$OSTYPE" == "msys" ]] ; then
    autobuild="$(cygpath -u "$AUTOBUILD")"
else
    autobuild="$AUTOBUILD"
fi

stage="$(pwd)/stage"
# nothing from an earlier run stays in the stage
rm -rf "$stage"
mkdir -p "$stage"

# load autobuild provided shell functions and variables
source_environment_tempfile="$stage/source_environment.sh"
"$autobuild" source_environment > "$source_environment_tempfile"
. "$source_environment_tempfile"

native() { if [[ "$OSTYPE" == "cygwin" || "$OSTYPE" == "msys" ]]; then cygpath -m "$1"; else echo "$1"; fi; }
# The source must be clean and exactly on neo-j2k's release tag v<version>: no local changes, no untracked files, no
# other commit. There is no override: a package is always the exact tag, and verify_package.py checks the same.
src="$(native "$SOURCE_DIR")"
if [ -n "$(git -C "$src" status --porcelain --untracked-files=all)" ]; then
    echo "neoj2k: the neo-j2k source is dirty (local changes or untracked files); refusing to build" >&2
    exit 1
fi
if tag="$(git -C "$src" describe --exact-match --tags --match 'v[0-9]*' HEAD 2>/dev/null)"; then
    NEOJ2K_VERSION="${tag#v}"
    echo "${NEOJ2K_VERSION}" > "${stage}/VERSION.txt"
else
    echo "neoj2k: the neo-j2k source is not exactly at a release tag v<version>; refusing to build" >&2
    exit 1
fi

build_dir="$(pwd)/build"
rm -rf "$build_dir" "$stage/install"
mkdir -p "$build_dir"

# The library alone: the oracle, harness, tools and bench stay out of the package build.
lib_options=(-DNJ2K_BUILD_STATIC=ON -DNJ2K_BUILD_SHARED=OFF -DNJ2K_MODULE_OPENJP2=OFF -DNJ2K_MSVC_STATIC_RUNTIME=OFF -DNJ2K_BUILD_TESTS=OFF -DNJ2K_BUILD_TOOLS=OFF
             -DNJ2K_BUILD_BENCH=OFF -DNJ2K_BUILD_FUZZERS=OFF -DNJ2K_INSTALL=ON -DNJ2K_SIMD=AVX2
             -DNJ2K_PROFILE_OPENSIM=OFF -DNJ2K_WERROR=OFF -DCMAKE_INSTALL_PREFIX="$(native "$stage/install")")

case "$AUTOBUILD_PLATFORM" in
    windows*)
        cmake -S "$(native "$SOURCE_DIR")" -B "$(native "$build_dir")" -G "${AUTOBUILD_WIN_CMAKE_GEN:-Visual Studio 18 2026}" -A x64 "${lib_options[@]}"
        cmake --build "$(native "$build_dir")" --config Release --parallel
        cmake --install "$(native "$build_dir")" --config Release
        mkdir -p "$stage/lib/release"
        cp "$stage/install/lib/neoj2k_static.lib" "$stage/lib/release/"
        ;;
    linux*)
        # The viewer's flags (-fno-stack-protector, the C++ standard the package sets itself) are the library's
        # own CMake rules; only the system-library floor matters here (glibc_report.py checks it in CI).
        cmake -S "$SOURCE_DIR" -B "$build_dir" -G Ninja -DCMAKE_BUILD_TYPE=Release "${lib_options[@]}"
        cmake --build "$build_dir" --config Release
        cmake --install "$(native "$build_dir")" --config Release
        mkdir -p "$stage/lib/release"
        cp "$stage/install/lib/libneoj2k.a" "$stage/lib/release/"
        ;;
    *)
        echo "neoj2k: no build for $AUTOBUILD_PLATFORM" >&2
        exit 1
        ;;
esac

# Only the two headers of the nj2k_* API; the install also holds the OpenJPEG-name headers, which stay out.
mkdir -p "$stage/include/neoj2k"
cp "$stage/install/include/neoj2k/neoj2k.h" "$stage/install/include/neoj2k/neoj2k.hpp" "$stage/include/neoj2k/"

mkdir -p "$stage/LICENSES"
# neoj2k.txt is the package's licence file: neo-j2k's licence, then OpenJPEG's with the notices of the code neo-j2k
# ports from it. openjpeg.txt is the second part alone, under the name OpenJPEG's own package uses.
{
    cat "$SOURCE_DIR/LICENSE"
    echo
    echo
    echo "----------------------------------------------------------------------------"
    echo "OpenJPEG (code ported into neo-j2k): licence and notices"
    echo "----------------------------------------------------------------------------"
    echo
    cat "$SOURCE_DIR/LICENSE.OpenJPEG"
} > "$stage/LICENSES/neoj2k.txt"
cp "$SOURCE_DIR/LICENSE.OpenJPEG" "$stage/LICENSES/openjpeg.txt"
cp "$SOURCE_DIR/NOTICE.md" "$stage/LICENSES/neoj2k-notice.md"

printf 'backend=cpu\nsimd=avx2\nprecise_fp=on\nstatic=1\nshared=0\nopenjpeg_shim=off\nthreads=none (the host lends an executor)\nprofile_opensim=off\n' > "$stage/BUILD_POLICY.txt"
git -C "$src" rev-parse HEAD > "$stage/SOURCE_REVISION.txt"
# nothing but the package files stays in the stage
rm -rf "$stage/install" "$source_environment_tempfile"
