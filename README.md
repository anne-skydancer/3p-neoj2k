<!-- SPDX-License-Identifier: BSD-2-Clause -->
# 3p-neoj2k

The autobuild package of [neo-j2k](https://github.com/anne-skydancer/neo-j2k) (BSD-2-Clause), the JPEG 2000 Part 1
codec of the Vulkanstorm viewer, built as a **shared library**: `neoj2k.dll` with its import library `neoj2k.lib`
(windows64), `libneoj2k.so` (linux64, and linux64-lts, built on ubuntu:24.04 with glibc 2.39 or lower, checked in
CI). It exports `nj2k_*` only, never starts a thread (the host lends an executor), keeps link-time code generation
inside the library, and needs an AVX2 processor.

The package is modelled on [3p-openjpeg](https://github.com/anne-skydancer/3p-openjpeg): `build-cmd.sh`,
`autobuild.xml`, `.github/workflows/build.yaml`, `verify_package.py`, a build-info file and a glibc report.

Contents: `include/neoj2k/` (the C API, the C++ wrapper, the OpenJPEG compatibility header and `compat/`),
`lib/release/`, and `LICENSES/` (neo-j2k's licence; OpenJPEG's, whose notices cover the code neo-j2k ports; the
repository's notice file; a build-info file). `BUILD_POLICY.txt` and `SOURCE_REVISION.txt` say how and from which
neo-j2k commit it was built.

The source is the `neo-j2k` submodule, pinned to one commit; releases are cut with the submodule on a commit of
neo-j2k's `main`. Local run: `NEOJ2K_SOURCE_DIR=<checkout> autobuild build -A 64 -c Release --no-configure` (with
`AUTOBUILD_VARIABLES_FILE` set as in the workflow), then `python verify_package.py stage <checkout>`.

Releasing: dispatch the Build workflow with `publish` and a `tag` (`v<version>-<n>`); the release carries the three
packages and `SHA256SUMS`, which the viewer's `autobuild.xml` entries need.
