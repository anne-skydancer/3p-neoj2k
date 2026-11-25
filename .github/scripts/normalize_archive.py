#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
# Copyright (c) 2026, Anne Skydancer (neo-j2k)
"""Rewrite a .tar.zst with root:root (0/0) owners, so the CI user's name and ids do not ship. Members, order, modes,
times and bytes stay as they are. usage: normalize_archive.py ARCHIVE.tar.zst"""
import io
import sys
import tarfile
from pathlib import Path

import zstandard

archive = Path(sys.argv[1])
members = []
with tarfile.open(fileobj=zstandard.ZstdDecompressor().stream_reader(archive.open('rb')), mode='r|') as tar:
    for m in tar:
        data = tar.extractfile(m).read() if m.isfile() else None
        m.uid = m.gid = 0
        m.uname = m.gname = 'root'
        members.append((m, data))
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode='w', format=tarfile.GNU_FORMAT) as out:
    for m, data in members:
        out.addfile(m, io.BytesIO(data) if data is not None else None)
archive.write_bytes(zstandard.ZstdCompressor(level=19).compress(buf.getvalue()))
