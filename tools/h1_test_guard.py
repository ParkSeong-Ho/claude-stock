"""
h1_test_guard.py — 전체 pytest 가 '바깥 세상'을 건드리지 않고, 환경·순서가 바뀌어도 같은 결과인지 확인하는 지킴이 (H1 단계 3).

무엇을 보나 (주식 초보용 설명: 시험이 진짜 인터넷·진짜 claude·진짜 장부를 건드리면 안 된다)
1. 인터넷: 파이썬 수준의 연결을 막고(부르면 기록 + OSError) 기록이 0 줄이어야 한다.
   막는 곳: socket.socket.connect·connect_ex, _socket.socket(C 소켓 형을 감싼 것으로 바꿔 끼움)의 connect·connect_ex,
   socket.create_connection, socket.getaddrinfo(localhost 밖), urllib.request.urlopen.
   - 방법: 임시 폴더의 sitecustomize.py 를 PYTHONPATH 맨 앞에 둔다. pytest 프로세스, 그리고 시험이 -I 없이 띄우는 파이썬
     하위 프로세스까지 실린다. subprocess.Popen 도 감싸서, 시험이 env 를 새로 주거나 PYTHONPATH 를 덮어써 하위 파이썬을
     띄워도 지킴이 폴더를 PYTHONPATH 맨 앞에 다시 붙인다. 기록 파일 경로는 sitecustomize 글자 안에 박혀 있어 env 와 상관없다.
   - 원래 sitecustomize(있으면, 예: 이 컨테이너의 zlib 고침)는 지킴이가 이어서 불러 준다.
   - **못 막는 길(정직하게)**: ① `python -I`(PYTHONPATH 를 무시 — T-ENTRY 등 3개 시험이 이렇게 띄움, 시세·claude 를 안 씀)
     ② os.execv*·os.posix_spawn 처럼 subprocess 를 거치지 않고 env 를 새로 준 하위 프로세스 ③ 파이썬 밖(ctypes 로 libc connect,
     C 로 만든 HTTP 라이브러리 — 이 venv 에 curl_cffi 가 깔려 있음, 저장소 코드는 안 씀 — curl 같은 다른 프로그램)
     ④ 지킴이보다 먼저 `from _socket import socket` 으로 잡아 둔 이름. 이런 길은 기록이 남지 않는다.
     → 리눅스에서는 `--netns` 로 pytest 전체를 네트워크가 없는 이름공간(`unshare -rn`)에서 돌리면 ①~④ 도 실제로는 나가지
       못한다(대신 기록은 없고 연결 실패로만 드러남). 맥에는 이 옵션이 없다(sandbox-exec 로 비슷하게 할 수 있으나 여기서는 안 함).
2. 진짜 claude: PATH 맨 앞에 '불리면 기록하고 실패(종료 코드 97)하는 가짜 claude'. 기록 파일 경로를 스크립트 안에 절대 경로로
   박아 env 를 새로 준 하위 프로세스가 불러도 기록된다. 기록이 0 줄이어야 한다. (PATH 를 통째로 바꾸거나 claude 를 절대 경로로
   부르면 못 잡는다 — 시험 파일마다의 지킴이(analyst·subprocess 바꿔 끼우기)가 그 몫.)
3. 결정성·순서: PYTHONHASHSEED(0·12345) × TZ(UTC·Asia/Seoul·America/New_York) 6번(LANG 은 C·C.UTF-8·ko_KR.UTF-8(있으면)을
   돌아가며) + 시험 항목 통째 역순 1번 + 시험 파일 순서를 정한 씨앗으로 섞은 1번. 시험마다 결과(통과·실패·건너뜀)가 모두 같아야
   한다. `--grid` 이면 씨앗 × TZ × LANG 전부. (파이썬 3.7+ 은 LANG=C 에서도 UTF-8 모드로 돈다 — 그래서 C.UTF-8·ko_KR 도 돈다.)
4. 저장소 깨끗함: 실행 앞뒤로 ① state/·results/ 아래 모든 파일(무시 파일 포함, 폴더가 이미 있어도)의 크기·수정 시각·sha256
   ② `git status --porcelain --ignored --untracked-files=all` ③ 그 목록의 추적 안 되는·무시되는 파일마다 크기·수정 시각·sha256
   을 견준다. 바이트코드 캐시(__pycache__·*.pyc)는 `python -I` 하위 프로세스가 PYTHONDONTWRITEBYTECODE 를 무시하고 써서
   따로 알리기만 한다(실패로 치지 않음). .pytest_cache·.ruff_cache 는 도구 캐시라 뺀다.

사용
  ~/.venv-cs/bin/python tools/h1_test_guard.py            # 전부(pytest 8번, 3개씩 함께)
  ~/.venv-cs/bin/python tools/h1_test_guard.py --quick    # 기본 1번 + 역순 1번 + 섞은 순서 1번
  ~/.venv-cs/bin/python tools/h1_test_guard.py --netns    # (리눅스) 네트워크 없는 이름공간에서
  ~/.venv-cs/bin/python tools/h1_test_guard.py -j 1 -- tests/test_h1_gaps.py   # pytest 대상 지정
  종료 코드 0 = 모두 통과, 1 = 하나라도 어긋남(화면에 무엇이 어긋났는지).
이 파일은 운영 코드가 아니다(CODE_FILES 밖, h1.py 가 읽지 않음). 저장소에 쓰지 않는다(임시 폴더만, 끝나면 예외가 나도 지움).
이 파일을 다른 폴더(예: 시험용 가짜 저장소)의 tools/ 에 복사해 두면 그 폴더를 저장소로 보고 돈다(맥 state/h1 흉내 시험이 이렇게 씀).
"""
from __future__ import annotations

import argparse
import hashlib
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
WATCH = ("state", "results")
TOOL_CACHES = (".pytest_cache/", ".ruff_cache/")
SHUFFLE_SEED = "20261104"

SITECUSTOMIZE = r'''
# h1 시험 지킴이(tools/h1_test_guard.py)가 PYTHONPATH 맨 앞에 넣는 파일. 인터넷을 막고, 부르려 한 흔적을 기록한다.
# 기록 파일·지킴이 폴더 경로는 아래에 글자로 박혀 있다(env 를 새로 준 하위 프로세스에서도 같은 곳에 기록).
import json as _json
import os as _os
import socket as _socket
import sys as _sys
import traceback as _tb

_LOG = __NETLOG__
_HERE = __GUARD_DIR__
_LOCAL = {None, "", "localhost", "127.0.0.1", "::1"}


def _note(kind, target):
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


_AF_UNIX = getattr(_socket, "AF_UNIX", object())
_real_connect = _socket.socket.connect
_real_connect_ex = _socket.socket.connect_ex
_real_gai = _socket.getaddrinfo


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

# C 소켓 형(_socket.socket)을 직접 쓰는 길: 감싼 형으로 바꿔 끼운다(지킴이보다 먼저 잡아 둔 이름은 못 막음).
import _socket as _csock   # noqa: E402

_RawBase = _csock.socket


class _GuardRawSocket(_RawBase):
    def connect(self, address):
        if self.family == _AF_UNIX:
            return _RawBase.connect(self, address)
        raise _blocked("_socket.socket.connect", address)

    def connect_ex(self, address):
        if self.family == _AF_UNIX:
            return _RawBase.connect_ex(self, address)
        _note("_socket.socket.connect_ex", address)
        return 101


_csock.socket = _GuardRawSocket

import urllib.request as _ur   # noqa: E402


def _urlopen(url, *a, **k):
    raise _blocked("urllib.request.urlopen", getattr(url, "full_url", url))


_ur.urlopen = _urlopen

# 하위 프로세스: env 를 새로 주거나 PYTHONPATH 를 덮어써도 지킴이 폴더를 PYTHONPATH 맨 앞에 다시 붙인다.
import subprocess as _sp   # noqa: E402

_RealPopen = _sp.Popen


class _GuardPopen(_RealPopen):
    def __init__(self, args, *a, **k):
        env = k.get("env")
        if env is not None:
            env = dict(env)
            parts = [x for x in (env.get("PYTHONPATH") or "").split(_os.pathsep) if x]
            if _HERE not in parts:
                env["PYTHONPATH"] = _os.pathsep.join([_HERE] + parts)
            k["env"] = env
        super().__init__(args, *a, **k)


_sp.Popen = _GuardPopen

# 원래 sitecustomize(있으면)를 이어서 부른다(이 컨테이너의 zlib 고침 등).
for _p in list(_sys.path):
    _d = _os.path.abspath(_p or ".")
    if _d == _HERE:
        continue
    _cand = _os.path.join(_d, "sitecustomize.py")
    if _os.path.isfile(_cand):
        import importlib.util as _iu
        _spec = _iu.spec_from_file_location("_h1_guard_next_sitecustomize", _cand)
        _mod = _iu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        break
'''

ORDER_PLUGIN = '''
# h1 시험 지킴이: 시험 순서 바꾸기.
#   H1_GUARD_REVERSE=1      모은 시험 항목을 통째로 거꾸로(파일 순서·파일 안 순서 모두)
#   H1_GUARD_SHUFFLE=<씨앗>  시험 파일 순서를 그 씨앗으로 섞음(파일 안 순서는 그대로 — 파일 범위 준비물이 한 번만 만들어지게)
import os
import random


def pytest_collection_modifyitems(session, config, items):
    if os.environ.get("H1_GUARD_REVERSE") == "1":
        items.reverse()
    seed = os.environ.get("H1_GUARD_SHUFFLE")
    if seed:
        groups = {}
        for it in items:
            groups.setdefault(it.nodeid.split("::")[0], []).append(it)
        keys = sorted(groups)
        random.Random(seed).shuffle(keys)
        items[:] = [it for k in keys for it in groups[k]]
'''

FAKE_CLAUDE = '''#!/bin/sh
# h1 시험 지킴이의 가짜 claude: 불리면 기록하고 실패한다(진짜 claude 를 부르면 안 됨). 기록 경로는 박혀 있음(env 무관).
echo "$$ $*" >> __CLAUDELOG__
exit 97
'''


def _locales():
    """쓸 수 있는 LANG 값: C, C.UTF-8(있으면), ko_KR.UTF-8(있으면, 맥의 보통 값)."""
    out = ["C"]
    for name in ("C.UTF-8", "ko_KR.UTF-8"):
        r = subprocess.run([sys.executable, "-c", f"import locale; locale.setlocale(locale.LC_ALL, {name!r})"],
                           capture_output=True)
        if r.returncode == 0:
            out.append(name)
    return out


def _variants(full: bool, quick: bool):
    langs = _locales()
    base = {"PYTHONHASHSEED": "0", "TZ": "UTC", "LANG": "C", "LC_ALL": "C"}
    rev = {"PYTHONHASHSEED": "12345", "TZ": "Asia/Seoul", "LANG": langs[-1], "LC_ALL": langs[-1], "H1_GUARD_REVERSE": "1"}
    shuf = {"PYTHONHASHSEED": "12345", "TZ": "America/New_York", "LANG": langs[min(1, len(langs) - 1)],
            "LC_ALL": langs[min(1, len(langs) - 1)], "H1_GUARD_SHUFFLE": SHUFFLE_SEED}
    if quick:
        return [("seed0-UTC-C", base), (f"reversed-seed12345-Seoul-{rev['LANG']}", rev),
                (f"shuffled{SHUFFLE_SEED}-seed12345-NewYork-{shuf['LANG']}", shuf)]
    out, i = [], 0
    for seed in ("0", "12345"):
        for tz, short in (("UTC", "UTC"), ("Asia/Seoul", "Seoul"), ("America/New_York", "NewYork")):
            for lang in (langs if full else [langs[i % len(langs)]]):
                out.append((f"seed{seed}-{short}-{lang}", {"PYTHONHASHSEED": seed, "TZ": tz, "LANG": lang, "LC_ALL": lang}))
            i += 1
    out.append((f"reversed-seed12345-Seoul-{rev['LANG']}", rev))
    out.append((f"shuffled{SHUFFLE_SEED}-seed12345-NewYork-{shuf['LANG']}", shuf))
    return out


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _stat(p: Path):
    if p.is_symlink():
        return ("link", os.readlink(p))
    if p.is_dir():
        return ("dir",)
    st = p.stat()
    return ("file", st.st_size, st.st_mtime_ns, _sha(p))


def _watch_snapshot(root: Path) -> dict:
    """state/·results/ 아래 모든 항목(무시 파일 포함, 폴더가 이미 있어도) — 크기·수정 시각·sha256."""
    out = {}
    for d in WATCH:
        base = root / d
        if not (base.exists() or base.is_symlink()):
            out[d] = None
            continue
        out[d] = _stat(base)
        if base.is_dir() and not base.is_symlink():
            for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
                for name in dirnames + filenames:
                    p = Path(dirpath) / name
                    out[p.relative_to(root).as_posix()] = _stat(p)
    return out


def _is_cache(rel: str) -> bool:
    return "__pycache__/" in rel or rel.endswith(".pyc")


def _git_snapshot(root: Path):
    """(git status --porcelain --ignored --untracked-files=all 줄 목록, 추적 안 되는·무시되는 파일마다 상태) 또는 None(git 아님)."""
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--ignored", "--untracked-files=all"],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    lines = [x for x in r.stdout.splitlines() if x.strip()]
    files = {}
    for x in lines:
        if x[:2] in ("??", "!!"):
            rel = x[3:].strip().strip('"')
            if rel.startswith(TOOL_CACHES) or _is_cache(rel):
                continue
            p = root / rel
            if p.exists() or p.is_symlink():
                files[rel] = _stat(p)
    return lines, files


def _diff(a: dict, b: dict) -> list:
    return [f"{k}: {a.get(k, '없음')} → {b.get(k, '없음')}" for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


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


def _run(work: Path, name: str, extra_env: dict, pytest_args: list, python: str, netns: bool) -> dict:
    xml = work / f"{name}.xml"
    env = dict(os.environ)
    env.update(extra_env)
    env["PYTHONPATH"] = str(work / "py") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PATH"] = str(work / "bin") + os.pathsep + env.get("PATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "h1_guard_order",
           f"--junitxml={xml}", "-o", "junit_family=xunit1", *pytest_args]
    if netns:
        cmd = ["unshare", "-rn", *cmd]
    r = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=3600)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    return {"name": name, "rc": r.returncode, "last": last,
            "outcomes": _outcomes(xml) if xml.exists() else {}, "tail": r.stdout[-3000:] + r.stderr[-2000:]}


def _lines(p: Path) -> list:
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="H1 시험 지킴이: 인터넷·claude·결정성·순서·저장소 깨끗함")
    ap.add_argument("--quick", action="store_true", help="기본 1번 + 역순 1번 + 섞은 순서 1번만")
    ap.add_argument("--grid", action="store_true", help="씨앗 × TZ × LANG 전부(오래 걸림)")
    ap.add_argument("--netns", action="store_true", help="(리눅스) unshare -rn 으로 네트워크 없는 이름공간에서")
    ap.add_argument("-j", type=int, default=3, help="함께 돌릴 pytest 수(기본 3)")
    ap.add_argument("--keep", action="store_true", help="임시 폴더(로그·junit xml)를 지우지 않음")
    ap.add_argument("--python", default=sys.executable, help="pytest 를 돌릴 파이썬(기본: 이 파이썬)")
    ap.add_argument("pytest_args", nargs="*", help="-- 뒤에 pytest 대상·옵션")
    a = ap.parse_args(argv)
    if a.netns and shutil.which("unshare") is None:
        print("[지킴이] --netns: unshare 가 없어요(리눅스 전용)")
        return 1
    work = Path(tempfile.mkdtemp(prefix="h1-test-guard-")).resolve()
    try:
        return _main(a, work)
    finally:
        if not a.keep:
            shutil.rmtree(work, ignore_errors=True)


def _main(a, work: Path) -> int:
    (work / "py").mkdir()
    (work / "bin").mkdir()
    netlog, claudelog = work / "net.log", work / "claude.log"
    site = SITECUSTOMIZE.replace("__NETLOG__", repr(str(netlog))).replace("__GUARD_DIR__", repr(str(work / "py")))
    (work / "py" / "sitecustomize.py").write_text(site, encoding="utf-8")
    (work / "py" / "h1_guard_order.py").write_text(ORDER_PLUGIN, encoding="utf-8")
    fake = work / "bin" / "claude"
    fake.write_text(FAKE_CLAUDE.replace("__CLAUDELOG__", "'" + str(claudelog).replace("'", "'\\''") + "'"),
                    encoding="utf-8")
    fake.chmod(0o755)
    variants = _variants(a.grid, a.quick)
    before_watch = _watch_snapshot(ROOT)
    before_git = _git_snapshot(ROOT)
    print(f"[지킴이] 저장소 {ROOT} · 임시 폴더 {work} · pytest {len(variants)}번(동시에 {a.j}개)"
          + (" · 네트워크 없는 이름공간" if a.netns else "") + f" · 대상 {a.pytest_args or '전체'}")
    with ThreadPoolExecutor(max(1, a.j)) as ex:
        runs = list(ex.map(lambda v: _run(work, v[0], v[1], a.pytest_args, a.python, a.netns), variants))
    problems, notes = [], []
    for r in runs:
        print(f"  {r['name']:<44} 종료 코드 {r['rc']} · {r['last']}")
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
    net, cl = _lines(netlog), _lines(claudelog)
    if net:
        problems.append(f"인터넷 시도 {len(net)}번: " + "; ".join(json.loads(x)["kind"] + " " + json.loads(x)["target"]
                                                           for x in net[:5]))
    if cl:
        problems.append(f"claude 호출 {len(cl)}번: {cl[:5]}")
    moved = _diff(before_watch, _watch_snapshot(ROOT))
    if moved:
        problems.append("시험 뒤 저장소 state/·results/ 가 바뀜(이미 있던 것 포함):\n    " + "\n    ".join(moved[:20]))
    after_git = _git_snapshot(ROOT)
    git_same = None
    if before_git is not None and after_git is not None:
        bl = [x for x in before_git[0] if not _is_cache(x)]
        al = [x for x in after_git[0] if not _is_cache(x)]
        cache_changed = sorted((set(before_git[0]) ^ set(after_git[0])) - set(bl) - set(al))
        git_same = bl == al and before_git[1] == after_git[1]
        if bl != al:
            problems.append("시험 뒤 git status(무시 파일 포함)가 바뀜:\n    "
                            + "\n    ".join(sorted(set(bl) ^ set(al))[:20]))
        fd = _diff(before_git[1], after_git[1])
        if fd:
            problems.append("시험 뒤 추적 안 되는·무시되는 파일 내용이 바뀜:\n    " + "\n    ".join(fd[:20]))
        if cache_changed:
            notes.append(f"바이트코드 캐시 목록 변화 {len(cache_changed)}줄(python -I 하위 프로세스가 씀 — 실패로 안 침)")
    print(f"[지킴이] 시험 {len(base)}개 결과 {dict(sorted(counts.items()))} · 실행 {len(runs)}번 모두 같음: "
          f"{all(r['outcomes'] == base for r in runs)}")
    print(f"[지킴이] 인터넷 시도 {len(net)}번 · claude 호출 {len(cl)}번 · state/·results/ 그대로: {not moved} · "
          f"git status(무시 파일·내용 포함) 그대로: {'git 아님' if git_same is None else git_same}")
    for n in notes:
        print(f"[지킴이] 참고: {n}")
    if problems:
        print("[지킴이] 어긋남:")
        for p in problems:
            print("  - " + p)
        return 1
    print("[지킴이] 모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
