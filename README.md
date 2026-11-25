<!-- SPDX-License-Identifier: BSD-2-Clause -->
# 3p-neoj2k

The autobuild package of [neo-j2k](https://github.com/anne-skydancer/neo-j2k) (BSD-2-Clause), the JPEG 2000 Part 1
codec for an app using this library, built as a **static library only**, with the OpenJPEG-compatible shim off.
The package has no shared library, no import library and no DLL or `.so`, and none of the OpenJPEG-name headers
(`neoj2k_openjpeg.h`, `compat/openjpeg.h`, `compat/opj_config.h`): the caller uses the `nj2k_*` API only. The shared
library and the OpenJPEG-compatible shim are distributed from the neo-j2k repository itself. The library is
`neoj2k_static.lib` (windows64) and `libneoj2k.a` (linux64, and linux64-lts, built on ubuntu:24.04 with glibc 2.39 or
lower, checked in CI). It starts no thread (the host lends an executor), needs an AVX2 processor and is built with
AVX2 and no OpenSim profile (CMake: `NJ2K_BUILD_STATIC=ON`, `NJ2K_BUILD_SHARED=OFF`, `NJ2K_MODULE_OPENJP2=OFF`).

Linking: define `NJ2K_STATIC` when compiling against the headers. It is built with the DLL C
runtime (`/MD`, as the viewer is) on Windows, so a consumer using `/MT` must not link it. On Linux it is position-independent
(`-fPIC`), so it also links into a shared object, and it needs only libc and libm. It carries no link-time-code-generation
objects, so any compiler version links it, and no global state or static initialisers (checked in CI by neo-j2k's
`check_objects.py`; CI also fails the build if the package holds a shared or import library, one of the three
OpenJPEG-name headers, an `opj_*` symbol, or any file outside the exact list below). The Windows file is `neoj2k_static.lib` because neo-j2k keeps `neoj2k.lib`
for the DLL's import library. The CMake package config (`neoj2kConfig*.cmake`) and `neoj2k.pc` are not shipped: the
package is consumed through autobuild, and the installed config (an export of the static target) points at `lib/neoj2k_static.lib`
and `include/`, while the package keeps the library in `lib/release/`, so it would be wrong.

The package is modelled on [3p-openjpeg](https://github.com/anne-skydancer/3p-openjpeg): `build-cmd.sh`,
`autobuild.xml`, `.github/workflows/build.yaml`, `verify_package.py`, a build-info file and a glibc report.

Contents, exactly (`verify_package.py` fails on anything else, in the stage and in each archive): `include/neoj2k/`
(`neoj2k.h`, the C API, and `neoj2k.hpp`, the C++ wrapper), `lib/release/` (the static library), `LICENSES/` (neo-j2k's
licence; OpenJPEG's, whose notices cover the code neo-j2k ports; the repository's notice file; a build-info file),
`BUILD_POLICY.txt` (static=1, shared=0, OpenJPEG shim off), `SOURCE_REVISION.txt` (the neo-j2k commit, equal to the
tag's commit) and `VERSION.txt`; the archive also holds the `autobuild-package.xml` that autobuild writes. Clean source: the build and CI fail if the neo-j2k submodule has local changes or is
not exactly at its release tag, and the licence files are checked byte for byte against neo-j2k's at that tag.

The source is the `neo-j2k` submodule, pinned to one commit; releases are cut with the submodule on a commit of
neo-j2k's `main`. Local run: `NEOJ2K_SOURCE_DIR=<checkout> autobuild build -A 64 -c Release --no-configure` (with
`AUTOBUILD_VARIABLES_FILE` set as in the workflow; the checkout must be clean and exactly on a release tag: there is no override),
then `python verify_package.py stage <checkout>`.

Releasing: tag neo-j2k's `main` commit `v<version>`, pin the submodule to it, then dispatch the Build workflow with
`publish` and the release tag `v<version>-<N>` (`N` the build number of this package for that neo-j2k version, e.g.
`v0.1.3-1`). The release job runs only from `main`, refuses a tag whose version is not the one the packages were built as or that exists
already, requires exactly the three archives, re-runs `verify_package.py --set` on them, and uploads only those archives and `SHA256SUMS`. The archives are
named `neoj2k-<version>-<platform>-<run id>.tar.zst` (platforms windows64, linux64, linux64-lts); the package version
(`VERSION.txt`) is neo-j2k's tag. The release
carries the three packages and `SHA256SUMS`, which the viewer's `autobuild.xml` entry needs (`license` BSD-2-Clause,
`license_file` LICENSES/neoj2k.txt, which holds neo-j2k's and OpenJPEG's notices).
