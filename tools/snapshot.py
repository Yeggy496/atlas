#!/usr/bin/env python
"""Version snapshots for the ATLAS-Σ demo (MASTER_SPEC §33 / §35).

This project follows a *no-Git* version discipline: every meaningful change is
captured as an immutable, self-describing snapshot under ``snapshots/`` so any
previous state can be reconstructed and diffed without a version-control server.

Usage::

    python tools/snapshot.py                      # snapshot the current VERSION
    python tools/snapshot.py --label "五维权重滑块"
    python tools/snapshot.py --bump patch         # 0.1.0 -> 0.1.1, then snapshot
    python tools/snapshot.py --list               # list existing snapshots
    python tools/snapshot.py --verify <name>      # checksum-check one snapshot

Design rules:
- No third-party dependencies (stdlib only), so it runs anywhere Python runs.
- Never mutate tracked source; snapshots are copies written under ``snapshots/``.
- Deterministic manifest: files are walked in sorted order and hashed with
  SHA-256, so two snapshots of the same tree are byte-identical.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = ROOT / 'snapshots'
VERSION_FILE = ROOT / 'VERSION'

# Directories that are never part of a snapshot: build output, caches, virtual
# environments, databases and the snapshots themselves.
EXCLUDE_DIRS = {
    '.venv', 'venv', '__pycache__', '.pytest_cache', 'node_modules',
    '.workbuddy-ai', 'snapshots', '.git', '.idea', '.vscode', 'dist',
    'build', 'coverage', '.mypy_cache', '.ruff_cache',
}
# Large or machine-specific artifacts that are reproducible and would bloat a
# snapshot. The verified frontend build lives in the repo but is regenerated at
# release time, so it is copied only on an explicit ``--with-dist`` run.
EXCLUDE_FILES = {'.env', 'atlas.db'}
EXCLUDE_SUFFIXES = {'.log', '.pid', '.tsbuildinfo'}
# Any ad-hoc scratch path (e.g. browser profiles from a verification run) never
# belongs in a version snapshot.
EXCLUDE_PREFIXES = ('_scratch',)


def read_version() -> str:
    if not VERSION_FILE.exists():
        return '0.0.0'
    return VERSION_FILE.read_text(encoding='utf-8').strip() or '0.0.0'


def write_version(value: str) -> None:
    VERSION_FILE.write_text(value + '\n', encoding='utf-8')


def bump(version: str, part: str) -> str:
    try:
        major, minor, patch = (int(x) for x in version.split('.'))
    except ValueError as exc:  # pragma: no cover - defensive
        raise SystemExit(f'VERSION 不是 vMAJOR.MINOR.PATCH 格式：{version!r}') from exc
    if part == 'major':
        major, minor, patch = major + 1, 0, 0
    elif part == 'minor':
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f'{major}.{minor}.{patch}'


def iter_files(with_dist: bool):
    """Yield files to snapshot, in a deterministic order."""
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if rel.parts and rel.parts[0].startswith(EXCLUDE_PREFIXES):
            continue
        if path.name in EXCLUDE_FILES or path.suffix in EXCLUDE_SUFFIXES:
            continue
        if not with_dist and rel.parts[:1] == ('frontend',) and 'dist' in rel.parts:
            continue
        yield rel, path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(label: str, with_dist: bool) -> Path:
    version = read_version()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    name = f'v{version}_{stamp}'
    target = SNAPSHOT_DIR / name
    target.mkdir(parents=True, exist_ok=True)

    manifest = {
        'version': version,
        'name': name,
        'label': label,
        'created_utc': stamp,
        'with_dist': with_dist,
        'files': [],
    }
    copied = 0
    for rel, src in iter_files(with_dist):
        dest = target / 'tree' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        manifest['files'].append(
            {'path': rel.as_posix(), 'sha256': sha256(src), 'bytes': src.stat().st_size}
        )
        copied += 1

    total_bytes = sum(f['bytes'] for f in manifest['files'])
    manifest['file_count'] = copied
    manifest['total_bytes'] = total_bytes
    (target / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    summary = (
        f'# Snapshot {name}\n'
        f'- 版本：v{version}\n'
        f'- 标签：{label or "（无）"}\n'
        f'- 创建（UTC）：{stamp}\n'
        f'- 文件数：{copied}\n'
        f'- 总字节：{total_bytes}\n'
        f'- 含前端构建产物：{"是" if with_dist else "否"}\n'
    )
    (target / 'README.md').write_text(summary, encoding='utf-8')
    return target


def list_snapshots() -> int:
    if not SNAPSHOT_DIR.exists():
        print('尚无快照。运行 python tools/snapshot.py 创建第一个。')
        return 0
    entries = sorted((p for p in SNAPSHOT_DIR.iterdir() if p.is_dir()), reverse=True)
    if not entries:
        print('尚无快照。')
        return 0
    print(f'共 {len(entries)} 个快照（{SNAPSHOT_DIR}）：')
    for entry in entries:
        manifest = entry / 'manifest.json'
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding='utf-8'))
            print(f'  {entry.name:32} v{data.get("version"):8} '
                  f'{data.get("file_count"):>4} 文件  {data.get("label") or ""}')
        else:
            print(f'  {entry.name:32} (缺少 manifest.json)')
    return 0


def verify(name: str) -> int:
    target = SNAPSHOT_DIR / name
    manifest = target / 'manifest.json'
    if not manifest.exists():
        print(f'未找到快照：{name}', file=sys.stderr)
        return 1
    data = json.loads(manifest.read_text(encoding='utf-8'))
    missing, mismatched, broken = 0, 0, 0
    for entry in data['files']:
        stored = target / 'tree' / entry['path']
        if not stored.exists():
            missing += 1
            continue
        if stored.stat().st_size != entry['bytes']:
            broken += 1
            continue
        if sha256(stored) != entry['sha256']:
            mismatched += 1
    print(f'校验 {name}：{len(data["files"])} 个文件')
    print(f'  缺失 {missing} · 校验和不符 {mismatched} · 字节不符 {broken}')
    if missing or mismatched or broken:
        print('  结果：损坏')
        return 1
    print('  结果：完整')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='ATLAS-Σ 版本快照工具（无 Git 版本纪律）')
    parser.add_argument('--label', default='', help='本次快照的说明标签')
    parser.add_argument('--bump', choices=['major', 'minor', 'patch'],
                        help='先递增 VERSION 再打快照')
    parser.add_argument('--with-dist', action='store_true',
                        help='一并包含 frontend/dist 构建产物')
    parser.add_argument('--list', action='store_true', help='列出已有快照')
    parser.add_argument('--verify', metavar='NAME', help='校验指定快照的完整性')
    args = parser.parse_args()

    if args.list:
        return list_snapshots()
    if args.verify:
        return verify(args.verify)

    if args.bump:
        new_version = bump(read_version(), args.bump)
        write_version(new_version)
        print(f'VERSION: -> {new_version}')

    target = snapshot(args.label, args.with_dist)
    print(f'已创建快照：{target.relative_to(ROOT)}')
    print('提示：快照目录默认被排除在后续快照之外，可安全保留或归档。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
