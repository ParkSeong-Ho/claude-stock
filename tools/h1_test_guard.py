"""
h1_test_guard.py — 전체 pytest 가 '바깥 세상'을 건드리지 않고, 환경이 바뀌어도 같은 결과인지 확인하는 지킴이 (H1 단계 3).

무엇을 보나 (주식 초보용 설명: 시험이 진짜 인터넷·진짜 claude·진짜 장부를 건드리면 안 된다)
1. 인터넷: socket.socket.connect·connect_ex·socket.create_connection·socket.getaddrinfo(바깥 이름)·
   urllib.request.urlopen 을 막고(부르면 기록 + OSError), 기록이 0 줄이어야 한다.
   - 막는 방법: PYTHONPATH 맨 앞의 sitecustomize.py. pytest 프로세스와 시험이 띄우는 파이썬 하위 프로세스
     (python h1.py … 처럼 -I 없이 띄우는 것)까지 막힌다. `python -I` 로 띄우는 짧은 스크립트(T-ENTRY 등)는
     PYTHONPATH 를 무시하므로 이 방법으로는 못 막는다(그 스크립트들은 시세·claude 를 쓰지 않는다).
   - 원래 sitecustomize(있으면, 예: 이 컨테이너의 zlib 고침)는 지킴이가 이어서 불러 준다.
2. 진짜 claude: PATH 맨 앞에 '불리면 기록을 남기고 실패하는 가짜 claude' 를 둔다. 기록이 0 줄이어야 한다.
3. 결정성: PYTHONHASHSEED(0·12345) × TZ(UTC·Asia/Seoul·America/New_York) × LANG=C 조합 6번 +
   시험 순서를 통째로 거꾸로(모든 시험 항목 역순 — 파일 순서와 파일 안 순서 둘 다) 1번 돌려,
   시험마다 결과(통과·실패·건너뜀)가 모두 같아야 한다.
4. 저장소: 시험 뒤 저장소에 state/·results/ 가 새로 생기지 않고 git status 가 그대로여야 한다.

사용
  ~/.venv-cs/bin/python tools/h1_test_guard.py            # 전부(전체 pytest 7번, 3개씩 함께 → 약 4~5분)
  ~/.venv-cs/bin/python tools/h1_test_guard.py --quick    # 기본 1번 + 역순 1번
  ~/.venv-cs/bin/python tools/h1_test_guard.py -j 1 -- tests/test_h1_gaps.py   # pytest 대상 지정
  종료 코드 0 = 모두 통과, 1 = 하나라도 어긋남(화면에 무엇이 어긋났는지).
이 파일은 운영 코드가 아니다(CODE_FILES 밖, h1.py 가 읽지 않음). 저장소 파일을 쓰지 않는다(임시 폴더만).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SITECUSTOMIZE = r'''
# h1 시험 지킴이(tools/h1_test_guard.py)가 PYTHONPATH 맨 앞에 넣는 파일. 인터넷을 막고, 부르려 한 흔적을 기록한다.
import json as _json
import os as _os
import socket as _socket
import sys as _sys
import traceback as _tb

_LOG = _os.environ.get("H1_GUARD_NETLOG")
_LOCAL = {None, "", "localhost", "127.0.0.1", "::1"}


def _note(kind, target):
    if _LOG:
        try:
            with open(_LOG, "a", encoding="utf-8") as f:
                f.write(_json.dumps({"pid": _os.getpid(), "kind": kind, "target": repr(target)[:200],
                                     "argv": [str(a) for a in _sys.argv[:4]],
                                     "stack": "".join(_tb.format_stack(limit=10)[:-1])}, ensure_ascii=False) + "\n")
        except OSError:
            pass


def _blocked(kind, target):
    _note(kind, target)
    return OSError(f"h1 시험 지킴이: 시험 중 인터넷 금지({kind} {target!r})")


_real_connect = _socket.socket.connect
_real_connect_ex = _socket.socket.connect_ex
_real_gai = _socket.getaddrinfo
_AF_UNIX = getattr(_socket, "AF_UNIX", object())


def _connect(self, address):
    if self.family == _AF_UNIX:
        return _real_connect(self, address)
    raise _blocked("socket.connect", address)


def _connect_ex(self, address):
    if self.family == _AF_UNIX:
        return _real_connect_ex(self, address)
    _note("socket.connect_ex", address)
    return 101   # ENETUNREACH


def _create_connection(address, *a, **k):
    raise _blocked("socket.create_connection", address)


def _getaddrinfo(host, *a, **k):
    if host in _LOCAL or (isinstance(host, (bytes, bytearray)) and host.decode(errors="replace") in _LOCAL):
        return _real_gai(host, *a, **k)
    raise _blocked("socket.getaddrinfo", host)


_socket.socket.connect = _connect
_socket.socket.connect_ex = _connect_ex
_socket.create_connection = _create_connection
_socket.getaddrinfo = _getaddrinfo

import urllib.request as _ur   # noqa: E402


def _urlopen(url, *a, **k):
    raise _blocked("urllib.request.urlopen", getattr(url, "full_url", url))


_ur.urlopen = _urlopen

# 원래 sitecustomize(있으면)를 이어서 부른다(이 컨테이너의 zlib 고침 등).
_here = _os.path.dirname(_os.path.abspath(__file__))
for _p in list(_sys.path):
    _d = _os.path.abspath(_p or ".")
    if _d == _here:
        continue
    _cand = _os.path.join(_d, "sitecustomize.py")
    if _os.path.isfile(_cand):
        import importlib.util as _iu
        _spec = _iu.spec_from_file_location("_h1_guard_next_sitecustomize", _cand)
        _mod = _iu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        break
'''

REVERSE_PLUGIN = '''
# h1 시험 지킴이: H1_GUARD_REVERSE=1 이면 모은 시험 항목을 통째로 거꾸로 돌린다(파일 순서·파일 안 순서 모두).
import os


def pytest_collection_modifyitems(session, config, items):
    if os.environ.get("H1_GUARD_REVERSE") == "1":
        items.reverse()
'''

FAKE_CLAUDE = '''#!/bin/sh
# h1 시험 지킴이의 가짜 claude: 불리면 기록하고 실패한다(진짜 claude 를 부르면 안 됨).
echo "$$ $*" >> "$H1_GUARD_CLAUDELOG"
exit 97
'''

VARIANTS = [
    ("seed0-UTC", {"PYTHONHASHSEED": "0", "TZ": "UTC", "LANG": "C", "LC_ALL": "C"}),
    ("seed0-Seoul", {"PYTHONHASHSEED": "0", "TZ": "Asia/Seoul", "LANG": "C", "LC_ALL": "C"}),
    ("seed0-NewYork", {"PYTHONHASHSEED": "0", "TZ": "America/New_York", "LANG": "C", "LC_ALL": "C"}),
    ("seed12345-UTC", {"PYTHONHASHSEED": "12345", "TZ": "UTC", "LANG": "C", "LC_ALL": "C"}),
    ("seed12345-Seoul", {"PYTHONHASHSEED": "12345", "TZ": "Asia/Seoul", "LANG": "C", "LC_ALL": "C"}),
    ("seed12345-NewYork", {"PYTHONHASHSEED": "12345", "TZ": "America/New_York", "LANG": "C", "LC_ALL": "C"}),
    ("reversed-seed12345-Seoul", {"PYTHONHASHSEED": "12345", "TZ": "Asia/Seoul", "LANG": "C", "LC_ALL": "C",
                                  "H1_GUARD_REVERSE": "1"}),
]


def _git_status():
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"],
                           capture_output=True, text=True, timeout=60)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _outcomes(xml_path: Path) -> dict:
    """junit xml → {시험 id: 'passed'|'failed'|'error'|'skipped'}."""
    out = {}
    for tc in ET.parse(xml_path).getroot().iter("testcase"):
        key = f"{tc.get('classname')}::{tc.get('name')}"
        kinds = {c.tag for c in tc}
        res = "failed" if "failure" in kinds else "error" if "error" in kinds else \
            "skipped" if "skipped" in kinds else "passed"
        if key in out and out[key] != "passed":            # 같은 id 가 두 번(setup error 등) → 나쁜 쪽
            continue
        out[key] = res
    return out


def _run(work: Path, name: str, extra_env: dict, pytest_args: list, python: str) -> dict:
    xml = work / f"{name}.xml"
    env = dict(os.environ)
    env.update(extra_env)
    env["PYTHONPATH"] = str(work / "py") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PATH"] = str(work / "bin") + os.pathsep + env.get("PATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["H1_GUARD_NETLOG"] = str(work / "net.log")
    env["H1_GUARD_CLAUDELOG"] = str(work / "claude.log")
    cmd = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "h1_guard_reverse",
           f"--junitxml={xml}", "-o", "junit_family=xunit1", *pytest_args]
    r = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=3600)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    return {"name": name, "rc": r.returncode, "last": last,
            "outcomes": _outcomes(xml) if xml.exists() else {}, "tail": r.stdout[-3000:] + r.stderr[-2000:]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="H1 시험 지킴이: 인터넷·claude·결정성·순서·저장소 깨끗함")
    ap.add_argument("--quick", action="store_true", help="기본 1번 + 역순 1번만")
    ap.add_argument("-j", type=int, default=3, help="함께 돌릴 pytest 수(기본 3)")
    ap.add_argument("--keep", action="store_true", help="임시 폴더(로그·junit xml)를 지우지 않음")
    ap.add_argument("--python", default=sys.executable, help="pytest 를 돌릴 파이썬(기본: 이 파이썬)")
    ap.add_argument("pytest_args", nargs="*", help="-- 뒤에 pytest 대상·옵션")
    a = ap.parse_args(argv)
    work = Path(tempfile.mkdtemp(prefix="h1-test-guard-"))
    (work / "py").mkdir()
    (work / "bin").mkdir()
    (work / "py" / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    (work / "py" / "h1_guard_reverse.py").write_text(REVERSE_PLUGIN, encoding="utf-8")
    fake = work / "bin" / "claude"
    fake.write_text(FAKE_CLAUDE, encoding="utf-8")
    fake.chmod(0o755)
    variants = [VARIANTS[0], VARIANTS[-1]] if a.quick else VARIANTS
    before_git = _git_status()
    before_dirs = {d: (ROOT / d).exists() for d in ("state", "results")}
    print(f"[지킴이] 임시 폴더 {work} · pytest {len(variants)}번(동시에 {a.j}개) · 대상 {a.pytest_args or '전체'}")
    with ThreadPoolExecutor(max(1, a.j)) as ex:
        runs = list(ex.map(lambda v: _run(work, v[0], v[1], a.pytest_args, a.python), variants))
    problems = []
    for r in runs:
        print(f"  {r['name']:<28} 종료 코드 {r['rc']} · {r['last']}")
        if r["rc"] != 0 or not r["outcomes"]:
            problems.append(f"{r['name']}: pytest 가 실패했거나 결과 파일이 없음\n{r['tail']}")
    base = runs[0]["outcomes"]
    for r in runs[1:]:
        if r["outcomes"] != base:
            only_a = sorted(set(base) - set(r["outcomes"]))[:10]
            only_b = sorted(set(r["outcomes"]) - set(base))[:10]
            diff = sorted(k for k in set(base) & set(r["outcomes"]) if base[k] != r["outcomes"][k])[:10]
            problems.append(f"결과가 {runs[0]['name']} 와 {r['name']} 에서 다름: 한쪽에만 {only_a} / {only_b}, "
                            f"결과 다름 {[(k, base[k], r['outcomes'][k]) for k in diff]}")
    counts = {}
    for k in base.values():
        counts[k] = counts.get(k, 0) + 1
    net = (work / "net.log").read_text(encoding="utf-8").splitlines() if (work / "net.log").exists() else []
    cl = (work / "claude.log").read_text(encoding="utf-8").splitlines() if (work / "claude.log").exists() else []
    if net:
        problems.append(f"인터넷 시도 {len(net)}번: " + "; ".join(json.loads(x)["kind"] + " " + json.loads(x)["target"]
                                                           for x in net[:5]))
    if cl:
        problems.append(f"claude 호출 {len(cl)}번: {cl[:5]}")
    for d, existed in before_dirs.items():
        if not existed and (ROOT / d).exists():
            problems.append(f"시험 뒤 저장소에 {d}/ 가 생김")
    after_git = _git_status()
    if before_git is not None and after_git != before_git:
        problems.append(f"시험 뒤 git status 가 바뀜:\n--- 전\n{before_git}--- 뒤\n{after_git}")
    print(f"[지킴이] 시험 {len(base)}개 결과 {dict(sorted(counts.items()))} · 실행 {len(runs)}번 모두 같음: "
          f"{all(r['outcomes'] == base for r in runs)}")
    print(f"[지킴이] 인터넷 시도 {len(net)}번 · claude 호출 {len(cl)}번 · state/·results/ 새로 생김: "
          f"{[d for d, e in before_dirs.items() if not e and (ROOT / d).exists()]} · git status 그대로: "
          f"{before_git is None or after_git == before_git}")
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    if problems:
        print("[지킴이] 어긋남:")
        for p in problems:
            print("  - " + p)
        return 1
    print("[지킴이] 모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
