#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) 2026, Anne Skydancer (neo-j2k)
"""Check the staged package: its layout and licences, the exports of the shared library (nj2k_* only, with the
library's own checker), and a lossless round trip through the shipped library from a program built against the
staged headers and import library.

usage: verify_package.py STAGE_DIR NEOJ2K_SOURCE_DIR
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

windows = os.name == 'nt'
stage = Path(sys.argv[1]).resolve()
source = Path(sys.argv[2]).resolve()
lib = stage / 'lib' / 'release'

required = ['VERSION.txt', 'BUILD_POLICY.txt', 'SOURCE_REVISION.txt', 'LICENSES/neoj2k.txt', 'LICENSES/openjpeg.txt',
            'LICENSES/neoj2k-notice.md', 'include/neoj2k/neoj2k.h', 'include/neoj2k/neoj2k.hpp',
            'include/neoj2k/neoj2k_openjpeg.h', 'include/neoj2k/compat/openjpeg.h']
required += (['lib/release/neoj2k.dll', 'lib/release/neoj2k.lib', 'lib/release/neoj2k_static.lib'] if windows
             else ['lib/release/libneoj2k.so', 'lib/release/libneoj2k.a'])
for name in required:
    assert (stage / name).is_file(), 'package file missing: ' + name
assert 'BSD 2-Clause' in (stage / 'LICENSES/neoj2k.txt').read_text(), 'neo-j2k licence text missing'
assert 'Copyright' in (stage / 'LICENSES/openjpeg.txt').read_text(), 'OpenJPEG notices missing'
combined = (stage / 'LICENSES/neoj2k.txt').read_text()
assert 'Anne Skydancer' in combined and 'Universite catholique de Louvain' in combined, 'the licence file must hold neo-j2k and OpenJPEG notices'
static = lib / ('neoj2k_static.lib' if windows else 'libneoj2k.a')

shared = lib / ('neoj2k.dll' if windows else 'libneoj2k.so')
subprocess.run([sys.executable, str(source / 'tools' / 'check_exports.py'), '--library', str(shared),
                '--header', str(stage / 'include/neoj2k/neoj2k.h'), '--list', str(source / 'abi' / 'exports.txt')], check=True)

# the static library: no global state, no initialisers, no link-time code generation (the library's own checker)
subprocess.run([sys.executable, str(source / 'tools' / 'check_objects.py'), '--library', str(static)], check=True)

def smoke(tmp, static_link):
    build = Path(tmp) / ('smoke_static' if static_link else 'smoke')
    here = Path(__file__).resolve().parent / 'tests'
    configure = ['cmake', '-S', str(here), '-B', str(build), '-DSTAGE=' + stage.as_posix(),
                 '-DNEOJ2K_STATIC_LINK=' + ('ON' if static_link else 'OFF')]
    if not windows:
        configure += ['-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release']
    subprocess.run(configure, check=True)
    subprocess.run(['cmake', '--build', str(build), '--config', 'Release'], check=True)
    exe = next(p for p in build.rglob('smoke' + ('.exe' if windows else '')) if p.is_file())
    if windows and not static_link:
        shutil.copy(shared, exe.parent)
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    print(result.stdout + result.stderr)
    assert result.returncode == 0, 'smoke test failed'
    assert 'smoke: PASS' in result.stdout

with tempfile.TemporaryDirectory() as tmp:
    smoke(tmp, False)
    smoke(tmp, True)
print('PASS: package layout, licences, exports, and a lossless round trip through the shared and the static library')
