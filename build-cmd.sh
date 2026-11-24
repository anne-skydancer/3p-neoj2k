#!/usr/bin/env bash
# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) 2026, Anne Skydancer (neo-j2k)
#
# Builds the neo-j2k shared library (neoj2k.dll with neoj2k.lib, libneoj2k.so) and the static library
# (neoj2k_static.lib, libneoj2k.a) from the pinned submodule and lays out the autobuild package:
#   include/neoj2k/        the public headers, with the OpenJPEG compatibility header and its compat/ names
#   lib/release/           neoj2k.dll + neoj2k.lib (the DLL's import library) + neoj2k_static.lib (Windows),
#                          libneoj2k.so, its soname link and libneoj2k.a (Linux)
#   LICENSES/              neo-j2k's licence, OpenJPEG's (the notices of the code neo-j2k ports), NOTICE.md
# The shared library exports nj2k_* only (tools/check_exports.py checks that), keeps link-time code generation
# inside, and the viewer delay-loads it. The static library is built from the same source with the same options
# (AVX2, no OpenSim profile), position-independent on Linux (the library's CMake always sets it, so the archive
# also links into a shared object) and with the DLL C runtime (/MD) on Windows, as the viewer builds with; it has
# no link-time code generation (so any compiler version links it) and no dependencies beyond libc and libm.
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
mkdir -p "$stage"

# load autobuild provided shell functions and variables
source_environment_tempfile="$stage/source_environment.sh"
"$autobuild" source_environment > "$source_environment_tempfile"
. "$source_environment_tempfile"

native() { if [[ "$OSTYPE" == "cygwin" || "$OSTYPE" == "msys" ]]; then cygpath -m "$1"; else echo "$1"; fi; }

# One version, in the public header (NJ2K_VERSION_*), as the library's CMakeLists reads it.
version_of() { sed -n -E "s/^#define NJ2K_VERSION_$1 ([0-9]+)\$/\1/p" "$SOURCE_DIR/include/neoj2k/neoj2k.h" | tr -d '\r'; }
NEOJ2K_VERSION="$(version_of MAJOR).$(version_of MINOR).$(version_of PATCH)"
build=${AUTOBUILD_BUILD_ID:=0}
# The package version is neo-j2k's own release when the pinned commit carries its tag (v<version>); any other
# commit is a pre-release build: <header version>.<build id>.
if tag="$(git -C "$(native "$SOURCE_DIR")" describe --exact-match --tags --match 'v[0-9]*' HEAD 2>/dev/null)"; then
    NEOJ2K_VERSION="${tag#v}"
    echo "${NEOJ2K_VERSION}" > "${stage}/VERSION.txt"
else
    echo "${NEOJ2K_VERSION}.${build}" > "${stage}/VERSION.txt"
fi

build_dir="$(pwd)/build"
rm -rf "$build_dir" "$stage/install"
mkdir -p "$build_dir"

# The library alone: the oracle, harness, tools and bench stay out of the package build.
lib_options=(-DNJ2K_BUILD_STATIC=ON -DNJ2K_BUILD_SHARED=ON -DNJ2K_MSVC_STATIC_RUNTIME=OFF -DNJ2K_BUILD_TESTS=OFF -DNJ2K_BUILD_TOOLS=OFF
             -DNJ2K_BUILD_BENCH=OFF -DNJ2K_BUILD_FUZZERS=OFF -DNJ2K_INSTALL=ON -DNJ2K_SIMD=AVX2
             -DNJ2K_PROFILE_OPENSIM=OFF -DNJ2K_WERROR=OFF -DCMAKE_INSTALL_PREFIX="$(native "$stage/install")")

case "$AUTOBUILD_PLATFORM" in
    windows*)
        cmake -S "$(native "$SOURCE_DIR")" -B "$(native "$build_dir")" -G "${AUTOBUILD_WIN_CMAKE_GEN:-Visual Studio 18 2026}" -A x64 "${lib_options[@]}"
        cmake --build "$(native "$build_dir")" --config Release --parallel
        cmake --install "$(native "$build_dir")" --config Release
        mkdir -p "$stage/lib/release"
        cp "$stage/install/bin/neoj2k.dll" "$stage/install/lib/neoj2k.lib" "$stage/install/lib/neoj2k_static.lib" "$stage/lib/release/"
        # the debug symbols, for crash dumps
        if [ -f "$build_dir/src/Release/neoj2k.pdb" ]; then cp "$build_dir/src/Release/neoj2k.pdb" "$stage/lib/release/"; fi
        ;;
    linux*)
        # The viewer's flags (-fno-stack-protector, the C++ standard the package sets itself) are the library's
        # own CMake rules; only the system-library floor matters here (glibc_report.py checks it in CI).
        cmake -S "$SOURCE_DIR" -B "$build_dir" -G Ninja -DCMAKE_BUILD_TYPE=Release "${lib_options[@]}"
        cmake --build "$build_dir" --config Release
        cmake --install "$(native "$build_dir")" --config Release
        mkdir -p "$stage/lib/release"
        # the file, its soname link and the development link, as the install made them
        cp -a "$stage"/install/lib/libneoj2k.so* "$stage/install/lib/libneoj2k.a" "$stage/lib/release/"
        ;;
    *)
        echo "neoj2k: no build for $AUTOBUILD_PLATFORM" >&2
        exit 1
        ;;
esac

mkdir -p "$stage/include"
cp -r "$stage/install/include/neoj2k" "$stage/include/neoj2k"

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

printf 'backend=cpu\nsimd=avx2\nprecise_fp=on\nshared_only=1\nthreads=none (the host lends an executor)\nprofile_opensim=off\n' > "$stage/BUILD_POLICY.txt"
git -C "$(native "$SOURCE_DIR")" rev-parse HEAD > "$stage/SOURCE_REVISION.txt"
rm -rf "$stage/install"
