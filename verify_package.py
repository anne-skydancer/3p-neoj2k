#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) 2026, Anne Skydancer (neo-j2k)
"""Check the package: its exact file list, licences, clean source, that it is static-only with the OpenJPEG shim off (no
shared library, no import library, none of the OpenJPEG-name headers, no opj_* symbols in the static library), and a
lossless round trip through the static library from a program built against the staged headers with NJ2K_STATIC.

usage: verify_package.py STAGE_DIR NEOJ2K_SOURCE_DIR
       verify_package.py --archive ARCHIVE.tar.zst   (the archive's exact file list only)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


def allowed(windows):
    """The exact file list of a package. Nothing else may be in the stage or the archive: no build-tree leftovers,
    tests, .git, temporary files, debug files, CMake or pkg-config files, or empty directories."""
    return {'VERSION.txt', 'BUILD_POLICY.txt', 'SOURCE_REVISION.txt',
            'LICENSES/neoj2k.txt', 'LICENSES/openjpeg.txt', 'LICENSES/neoj2k-notice.md', 'LICENSES/neoj2k-buildinfo.json',
            'include/neoj2k/neoj2k.h', 'include/neoj2k/neoj2k.hpp',
            'lib/release/' + ('neoj2k_static.lib' if windows else 'libneoj2k.a')}


def check_listing(files, dirs, windows, extra=()):
    want = allowed(windows)
    extras = {e for e in extra if e in files}
    unexpected = sorted(files - want - extras)
    missing = sorted(want - files)
    assert not unexpected, 'files not on the allowlist: ' + ', '.join(unexpected)
    assert not missing, 'files missing: ' + ', '.join(missing)
    parents = set()
    for f in files:
        parents.update(q.as_posix() for q in Path(f).parents)
    for d in dirs:
        assert d in parents or d in ('', '.'), 'empty directory: ' + d


def norm(name):
    name = name[2:] if name.startswith('./') else name
    return name.rstrip('/')


if sys.argv[1] == '--archive':
    archive = Path(sys.argv[2])
    try:
        import zstandard
        tar = tarfile.open(fileobj=zstandard.ZstdDecompressor().stream_reader(archive.open('rb')), mode='r|')
    except ImportError:
        from compression import zstd  # Python 3.14
        tar = tarfile.open(fileobj=zstd.open(archive), mode='r|')
    files, dirs = set(), set()
    for m in tar:
        if m.isfile():
            files.add(norm(m.name))
        elif m.isdir():
            dirs.add(norm(m.name))
        else:
            raise AssertionError('neither a plain file nor a directory in the archive: ' + m.name)
    print('\n'.join(sorted(files)))
    check_listing(files, dirs, 'windows' in archive.name, extra=('autobuild-package.xml',))
    print('PASS: the archive holds exactly the allowlisted files: ' + archive.name)
    sys.exit(0)

windows = os.name == 'nt'
stage = Path(sys.argv[1]).resolve()
source = Path(sys.argv[2]).resolve()
lib = stage / 'lib' / 'release'
static = lib / ('neoj2k_static.lib' if windows else 'libneoj2k.a')

files = {p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file()}
dirs = {p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_dir()}
print('\n'.join(sorted(files)))
check_listing(files, dirs, windows)
for pattern in ('*.dll', '*.so', '*.so.*', '*.dylib', '*.pdb', 'neoj2k.lib', '*.cmake', '*.pc'):
    found = [p.relative_to(stage).as_posix() for p in stage.rglob(pattern)]
    assert not found, 'shared, import, debug or config files must not be packaged: ' + ', '.join(found)
for dropped in ('include/neoj2k/neoj2k_openjpeg.h', 'include/neoj2k/compat/openjpeg.h', 'include/neoj2k/compat/opj_config.h'):
    assert not (stage / dropped).exists(), 'header of the OpenJPEG shim must not be packaged: ' + dropped


def git(*args):
    return subprocess.run(['git', '-C', str(source)] + list(args), capture_output=True, text=True, check=True).stdout.strip()


# clean source: no local changes, exactly at the release tag, and the package says so
assert not git('status', '--porcelain', '--untracked-files=all'), 'the neo-j2k source is dirty'
tag = git('describe', '--exact-match', '--tags', '--match', 'v[0-9]*', 'HEAD')
version = (stage / 'VERSION.txt').read_text().strip()
assert re.fullmatch(r'\d+\.\d+\.\d+', version), 'the version must be plain X.Y.Z: ' + version
assert version == tag[1:], 'VERSION.txt (%s) must equal the source tag (%s)' % (version, tag)
revision = (stage / 'SOURCE_REVISION.txt').read_text().strip()
assert revision == git('rev-parse', tag + '^{commit}') == git('rev-parse', 'HEAD'), 'SOURCE_REVISION.txt must be the tag commit'
meta = {n: (stage / n).read_text() for n in ('VERSION.txt', 'BUILD_POLICY.txt', 'SOURCE_REVISION.txt', 'LICENSES/neoj2k-buildinfo.json')}
for n, text in meta.items():
    assert not re.search(r'dirty|\+local', text, re.I), n + ' carries a dirty or local marker'
assert not re.search(rb'\d+\.\d+\.\d+(-dirty|\+dirty|\+local)', static.read_bytes()), 'the library carries a dirty or local version string'

# clean archive: no host paths in the metadata; licence texts byte-identical to neo-j2k's at the tag
host_path = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|/home/|/Users/|/root/|/runner/|/__w/')
for n, text in meta.items():
    assert not host_path.search(text), n + ' leaks a host path'
    assert str(stage) not in text and str(Path.cwd()) not in text, n + ' leaks a host path'


def src(n):
    return (source / n).read_bytes()


def pkg(n):
    return (stage / n).read_bytes()


assert pkg('LICENSES/openjpeg.txt') == src('LICENSE.OpenJPEG'), 'openjpeg.txt differs from neo-j2k LICENSE.OpenJPEG'
assert pkg('LICENSES/neoj2k-notice.md') == src('NOTICE.md'), 'neoj2k-notice.md differs from neo-j2k NOTICE.md'
assert pkg('LICENSES/neoj2k.txt').startswith(src('LICENSE')) and pkg('LICENSES/neoj2k.txt').endswith(src('LICENSE.OpenJPEG')), \
    'neoj2k.txt must be neo-j2k LICENSE then LICENSE.OpenJPEG, byte for byte'
assert 'BSD 2-Clause' in (stage / 'LICENSES/neoj2k.txt').read_text(), 'neo-j2k licence text missing'
combined = (stage / 'LICENSES/neoj2k.txt').read_text()
assert 'Anne Skydancer' in combined and 'Universite catholique de Louvain' in combined, 'the licence file must hold neo-j2k and OpenJPEG notices'

# the metadata says static-only, shim off
policy = meta['BUILD_POLICY.txt']
assert 'static=1' in policy and 'shared=0' in policy and 'openjpeg_shim=off' in policy, 'BUILD_POLICY.txt must say static-only, shim off'
opts = json.loads(meta['LICENSES/neoj2k-buildinfo.json'])['configure_options']
for o in ('NJ2K_BUILD_STATIC=ON', 'NJ2K_BUILD_SHARED=OFF', 'NJ2K_MODULE_OPENJP2=OFF', 'NJ2K_SIMD=AVX2', 'NJ2K_PROFILE_OPENSIM=OFF'):
    assert o in opts, 'the build-info json must record ' + o

# the static library: no global state, no initialisers, no link-time code generation (the library's own checker)
subprocess.run([sys.executable, str(source / 'tools' / 'check_objects.py'), '--library', str(static)], check=True)


# no opj_* symbols: the shim is off. nm or llvm-nm where there is one, dumpbin on Windows, else a scan of the bytes
def symbols():
    for tool in (['nm', '-A'], ['llvm-nm', '-A'], ['dumpbin', '/symbols']):
        if shutil.which(tool[0]):
            r = subprocess.run(tool + [str(static)], capture_output=True, text=True, errors='replace')
            if r.returncode == 0 and r.stdout.strip():
                print('symbols listed with ' + tool[0])
                return r.stdout
    print('no symbol tool found: scanning the archive bytes')
    return static.read_bytes().decode('latin-1')


opj = sorted(set(re.findall(r'[A-Za-z0-9_.$@?]*(?<![A-Za-z0-9])opj_\w*', symbols())))
assert not opj, 'the static library must not contain opj_* symbols: ' + ', '.join(opj[:10])


def smoke(tmp):
    build = Path(tmp) / 'smoke_static'
    here = Path(__file__).resolve().parent / 'tests'
    configure = ['cmake', '-S', str(here), '-B', str(build), '-DSTAGE=' + stage.as_posix()]
    if not windows:
        configure += ['-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release']
    subprocess.run(configure, check=True)
    subprocess.run(['cmake', '--build', str(build), '--config', 'Release'], check=True)
    exe = next(p for p in build.rglob('smoke' + ('.exe' if windows else '')) if p.is_file())
    result = subprocess.run([str(exe)], capture_output=True, text=True)
    print(result.stdout + result.stderr)
    assert result.returncode == 0, 'smoke test failed'
    assert 'smoke: PASS' in result.stdout


with tempfile.TemporaryDirectory() as tmp:
    smoke(tmp)
print('PASS: exact file list, clean source at ' + tag + ', licences, static-only without shim symbols, and a lossless round trip through the static library')
