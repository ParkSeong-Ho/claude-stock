"""
h1_repo_guard.py — 시험이 저장소 안(state/·results/)을 건드리지 않았는지 보는 도우미. 시험 파일이 아니라 pytest 가 모으지 않는다.

왜 (단계 3 검토 T-3): 맥 운영 체크아웃·H1 전용 worktree 에는 state/ 가 이미 있고, H1 을 start 한 뒤면 state/h1/ 에 진짜 장부가 있다.
그래서 "state/ 가 없다가 생겼는지"만 보면 시험이 그 안의 파일을 고치거나 새 파일을 만들어도 모른다.
- snapshot(root): state/·results/ 아래 모든 항목(폴더·파일·심볼릭 링크, git 이 무시하는 파일 포함)의 (종류, 크기, 수정 시각 ns)
  — hash_files=True 이면 파일 sha256 까지. 폴더가 없으면 그 폴더 칸은 None.
- changes(before, after): 달라진 항목을 읽기 쉬운 글 목록으로(없으면 빈 목록).
시험마다(앞뒤로) 쓰는 fixture 는 sha256 없이 견준다(시험 수백 개 × 맥 state/ 의 파일 수 MB 를 매번 해시하면 느림 — 쓰면 크기나
수정 시각이 바뀐다). 지킴이 tools/h1_test_guard.py 는 전체 실행 앞뒤로 sha256 까지 본다.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

WATCH = ("state", "results")


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(root, watch=WATCH, hash_files=False) -> dict:
    root = Path(root)
    out = {}
    for d in watch:
        base = root / d
        if not (base.exists() or base.is_symlink()):
            out[d] = None
            continue
        out[d] = ("dir" if base.is_dir() else "other",)
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            for name in sorted(dirnames) + sorted(filenames):
                p = Path(dirpath) / name
                rel = p.relative_to(root).as_posix()
                st = p.lstat()
                if p.is_symlink():
                    out[rel] = ("link", os.readlink(p))
                elif p.is_dir():
                    out[rel] = ("dir",)
                else:
                    out[rel] = ("file", st.st_size, st.st_mtime_ns) + ((_sha(p),) if hash_files else ())
    return out


def changes(before: dict, after: dict) -> list:
    out = []
    for k in sorted(set(before) | set(after)):
        a, b = before.get(k, "없음"), after.get(k, "없음")
        if a != b:
            out.append(f"{k}: {a} → {b}")
    return out
