#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) 2026, Anne Skydancer (neo-j2k)
"""Check the package: its exact file list, licences, clean source, that it is static-only with the openjp2 module off (no
shared library, no import library, none of the OpenJPEG-name headers, no opj_* symbols in the static library), and a
lossless round trip through the static library from a program built against the staged headers with NJ2K_STATIC.

usage: verify_package.py STAGE_DIR NEOJ2K_SOURCE_DIR
       verify_package.py --archive ARCHIVE.tar.zst [STAGE_DIR]
           the archive's file list, tar owners and metadata files; with STAGE_DIR, every member byte-identical to the stage
       verify_package.py --set DIR
           the release set: exactly one archive each for windows64, linux64 and linux64-lts, each checked as above,
           one version, one SOURCE_REVISION.txt, identical licence files and headers
"""
import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

if not __debug__:
    sys.exit('verify_package.py must not run under python -O (its checks are asserts)')

PLATFORMS = ('windows64', 'linux64', 'linux64-lts')
# The options build-cmd.sh configures with (lib_options). The build-info json and the build's CMakeCache.txt must both
# hold exactly these values.
OPTIONS = {'NJ2K_BUILD_STATIC': 'ON', 'NJ2K_BUILD_SHARED': 'OFF', 'NJ2K_MODULE_OPENJP2': 'OFF', 'NJ2K_MSVC_STATIC_RUNTIME': 'OFF',
           'NJ2K_SIMD': 'AVX2', 'NJ2K_PROFILE_OPENSIM': 'OFF'}
METADATA = ('VERSION.txt', 'BUILD_POLICY.txt', 'SOURCE_REVISION.txt', 'LICENSES/neoj2k-buildinfo.json')
HOST_PATH = re.compile(r'(?<![A-Za-z])[A-Za-z]:[\\/]|/home/|/Users/|/root/|/runner/|/__w/|/tmp/|/mnt/|/opt/')


def allowed(windows):
    """The exact file list of a package. Nothing else may be in the stage or the archive: no build-tree leftovers,
    tests, .git, temporary files, debug files, CMake or pkg-config files, shared or import libraries, the
    OpenJPEG-name headers, or empty directories."""
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


def check_metadata(root, extra_text=()):
    """Content checks on the metadata files of a stage or an extracted archive: no dirty or local marker, no host path,
    no carriage return, a plain version, static-only and openjp2 module off, the options recorded. Returns the metadata texts."""
    meta = {n: (root / n).read_text() for n in METADATA}
    texts = dict(meta)
    for n in extra_text:
        if (root / n).exists():
            texts[n] = (root / n).read_text()
    for n, text in texts.items():
        assert not re.search(r'dirty|\+local', text, re.I), n + ' carries a dirty or local marker'
        assert not HOST_PATH.search(text), n + ' leaks a host path'
    for n, text in meta.items():
        assert '\r' not in text, n + ' has a carriage return'
    assert re.fullmatch(r'\d+\.\d+\.\d+', meta['VERSION.txt'].strip()), 'the version must be plain X.Y.Z: ' + meta['VERSION.txt']
    assert re.fullmatch(r'[0-9a-f]{40}', meta['SOURCE_REVISION.txt'].strip()), 'SOURCE_REVISION.txt must be one commit hash'
    policy = meta['BUILD_POLICY.txt']
    assert 'static=1' in policy and 'shared=0' in policy and 'openjp2_module=off' in policy, 'BUILD_POLICY.txt must say static-only, openjp2 module off'
    opts = json.loads(meta['LICENSES/neoj2k-buildinfo.json'])['configure_options']
    for k, v in OPTIONS.items():
        assert k + '=' + v in opts, 'the build-info json must record %s=%s' % (k, v)
    return meta


def open_tar(archive):
    try:
        import zstandard
        return tarfile.open(fileobj=zstandard.ZstdDecompressor().stream_reader(archive.open('rb')), mode='r|')
    except ImportError:
        from compression import zstd  # Python 3.14
        return tarfile.open(fileobj=zstd.open(archive), mode='r|')


def norm(name):
    name = name[2:] if name.startswith('./') else name
    return name.rstrip('/')


def platform_of(archive):
    m = re.fullmatch(r'neoj2k-\d+\.\d+\.\d+-(windows64|linux64-lts|linux64)-\d+\.tar\.zst', archive.name)
    assert m, 'archive name must be neoj2k-<X.Y.Z>-<windows64|linux64|linux64-lts>-<run id>.tar.zst: ' + archive.name
    return m.group(1)


def check_archive(archive, stage, out):
    """List, extract (into the empty directory out) and check one archive. Returns its platform."""
    platform = platform_of(archive)
    files, dirs = set(), set()
    with open_tar(archive) as tar:
        for m in tar:
            assert m.uname in ('root', '') and m.gname in ('root', '') and m.uid == 0 and m.gid == 0, \
                'tar owner of %s is %s/%s (%d/%d), not root' % (m.name, m.uname, m.gname, m.uid, m.gid)
            name = norm(m.name)
            if m.isfile():
                files.add(name)
                target = out / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(m).read())
            elif m.isdir():
                dirs.add(name)
            else:
                raise AssertionError('neither a plain file nor a directory in the archive: ' + m.name)
    print('\n'.join(sorted(files)))
    check_listing(files, dirs, platform.startswith('windows'), extra=('autobuild-package.xml',))
    check_metadata(out, extra_text=('autobuild-package.xml',))
    if stage is not None:
        for f in sorted(files - {'autobuild-package.xml'}):
            assert filecmp.cmp(out / f, stage / f, shallow=False), 'archive member differs from the verified stage: ' + f
    print('PASS: the archive holds exactly the allowlisted files, with clean metadata: ' + archive.name)
    return platform


if len(sys.argv) < 3:
    sys.exit(__doc__)

if sys.argv[1] == '--archive':
    with tempfile.TemporaryDirectory() as tmp:
        check_archive(Path(sys.argv[2]), Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None, Path(tmp))
    sys.exit(0)

if sys.argv[1] == '--set':
    got = {}
    with tempfile.TemporaryDirectory() as tmp:
        for a in sorted(Path(sys.argv[2]).glob('*.tar.zst')):
            out = Path(tmp) / a.name
            out.mkdir()
            platform = check_archive(a, None, out)
            assert platform not in got, 'two archives for ' + platform
            got[platform] = out
        assert sorted(got) == sorted(PLATFORMS), 'the release needs exactly one archive each for %s, found %s' % (PLATFORMS, sorted(got))
        for n in ('VERSION.txt', 'SOURCE_REVISION.txt', 'LICENSES/neoj2k.txt', 'LICENSES/openjpeg.txt', 'LICENSES/neoj2k-notice.md',
                  'include/neoj2k/neoj2k.h', 'include/neoj2k/neoj2k.hpp'):
            for p in PLATFORMS[1:]:
                assert filecmp.cmp(got[PLATFORMS[0]] / n, got[p] / n, shallow=False), '%s differs between %s and %s' % (n, PLATFORMS[0], p)
    print('PASS: the release set is three clean archives of one version, one source commit and one set of licences and headers')
    sys.exit(0)

windows = os.name == 'nt'
stage = Path(sys.argv[1]).resolve()
source = Path(sys.argv[2]).resolve()
lib = stage / 'lib' / 'release'
static = lib / ('neoj2k_static.lib' if windows else 'libneoj2k.a')

files = {p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file()}
dirs = {p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_dir()}
print('\n'.join(sorted(files)))
check_listing(files, dirs, windows, extra=('autobuild-package.xml',))


def git(*args):
    return subprocess.run(['git', '-C', str(source)] + list(args), capture_output=True, text=True, check=True).stdout.strip()


# Clean source and exact commit provenance, including validation builds before a release tag.
assert not git('status', '--porcelain', '--untracked-files=all', '--ignored'), 'the neo-j2k source is dirty'
meta = check_metadata(stage)
version = meta['VERSION.txt'].strip()
revision = git('rev-parse', 'HEAD')
assert meta['SOURCE_REVISION.txt'].strip() == revision, 'SOURCE_REVISION.txt must be the source commit'


def src(n):
    return (source / n).read_bytes()


def pkg(n):
    return (stage / n).read_bytes()


# The version the library reports comes from the source and staged public headers.
for h in (source / 'include/neoj2k/neoj2k.h', stage / 'include/neoj2k/neoj2k.h'):
    text = h.read_text()
    v = '.'.join(re.search(r'^#define NJ2K_VERSION_%s (\d+)\s*$' % k, text, re.M).group(1) for k in ('MAJOR', 'MINOR', 'PATCH'))
    assert v == version, '%s says %s, VERSION.txt says %s' % (h, v, version)
assert pkg('include/neoj2k/neoj2k.h') == src('include/neoj2k/neoj2k.h') and pkg('include/neoj2k/neoj2k.hpp') == src('include/neoj2k/neoj2k.hpp'), \
    'the staged headers must be the source headers byte for byte'

# the options recorded are the options CMake used
cache = {}
for line in (Path(__file__).resolve().parent / 'build' / 'CMakeCache.txt').read_text().splitlines():
    m = re.match(r'([A-Za-z0-9_]+):[A-Z]+=(.*)$', line)
    if m:
        cache[m.group(1)] = m.group(2)
for k, v in OPTIONS.items():
    assert cache.get(k) == v, 'CMakeCache.txt has %s=%s, the package build must use %s' % (k, cache.get(k), v)

# clean archive: licence texts byte-identical to neo-j2k's at the tag
assert pkg('LICENSES/openjpeg.txt') == src('LICENSE.OpenJPEG'), 'openjpeg.txt differs from neo-j2k LICENSE.OpenJPEG'
assert pkg('LICENSES/neoj2k-notice.md') == src('NOTICE.md'), 'neoj2k-notice.md differs from neo-j2k NOTICE.md'
assert pkg('LICENSES/neoj2k.txt').startswith(src('LICENSE')) and pkg('LICENSES/neoj2k.txt').endswith(src('LICENSE.OpenJPEG')), \
    'neoj2k.txt must be neo-j2k LICENSE then LICENSE.OpenJPEG, byte for byte'
assert 'BSD 2-Clause' in (stage / 'LICENSES/neoj2k.txt').read_text(), 'neo-j2k licence text missing'
combined = (stage / 'LICENSES/neoj2k.txt').read_text()
assert 'Anne Skydancer' in combined and 'Universite catholique de Louvain' in combined, 'the licence file must hold neo-j2k and OpenJPEG notices'

# the static library: no global state, no initialisers, no link-time code generation (the library's own checker)
subprocess.run([sys.executable, str(source / 'tools' / 'check_objects.py'), '--library', str(static)], check=True)


# no exported opj_* symbols: the openjp2 module is off (file-local names such as MSVC's unwind-chain symbols of internal functions
# do not count). The listing must come from a symbol tool and must show the library's own nj2k_ API.
def symbols():
    for tool in (['nm', '-A', '-g', '--defined-only'], ['llvm-nm', '-A', '-g', '--defined-only'], ['dumpbin', '/symbols']):
        if shutil.which(tool[0]):
            r = subprocess.run(tool + [str(static)], capture_output=True, text=True, errors='replace')
            if r.returncode == 0 and r.stdout.strip():
                print('symbols listed with ' + tool[0])
                return r.stdout
    raise AssertionError('no symbol tool (nm, llvm-nm, dumpbin) listed the static library')


# a symbol is the last word of a line; string literals (MSVC's ??_C@... of __func__ texts) are data, not names of the library
names = {l.split()[-1] for l in symbols().splitlines() if l.split()}
assert any(re.fullmatch(r'_?nj2k_version', w) for w in names), 'the symbol listing does not show nj2k_version: the check would be vacuous'
opj = sorted(w for w in names if re.match(r'[_?]?opj_', w))
assert not opj, 'the static library must not contain opj_* symbols: ' + ', '.join(opj[:10])


def smoke(tmp):
    build = Path(tmp) / 'smoke_static'
    here = Path(__file__).resolve().parent / 'tests'
    configure = ['cmake', '-S', str(here), '-B', str(build), '-DSTAGE=' + stage.as_posix(), '-DEXPECT_VERSION=' + version]
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
print('PASS: exact file list, clean source at ' + revision + ', licences, static-only without opj_* symbols, version, and a lossless round trip through the static library')
