"""T-GOLD (설계 docs/h1-forward-design.md §6, §7 R13) — 운영 동작이 '바꾸기 전'과 바이트까지 같은지.

- 골든 `tests/golden/` 은 코드를 고치기 전 커밋(847ad13)을 따로 꺼낸 git worktree 에서
  `tests/golden_scenarios.py` 로 만들었다(만든 날짜·명령·장면 목록·기준 버전은 tests/golden/README.md).
- 이 시험은 같은 장면을 **지금 코드**로 다시 돌려, 파일 목록과 내용(상태 JSON·화면 출력·팀장 호출·스크리너 결과)이
  골든과 바이트까지 같은지 본다. 다르면 어느 파일이 어떻게 다른지 읽기 쉽게 보여 주고,
  지금 라이브러리 버전이 골든을 만든 버전과 다르면 그 사실도 같이 알린다(거짓 경보일 수 있음, 2a 검토 A-11).
- 골든 파일이 빠짐없이 있고 git 이 무시하지 않는지도 본다(2a 검토 A-1: `.gitignore` 의 `state/` 에 걸려 빠졌던 일).
- 장면이 정말 그 가지(서킷·정지·멱등·22:30·받기 실패 …)를 지나는지도 다시 확인한다.
- 인터넷·claude·키 없이 돈다(입출력 경계만 가짜로 바꿔 끼움, golden_scenarios.py 설명).
"""
import difflib
import platform
import re
import shutil
import subprocess
import sys
import unicodedata
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import golden_scenarios as gs   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).resolve().parent / "golden"
README = GOLDEN / "README.md"
MARKETS = ("us", "kr")
_CACHE = {}


def _run(market):
    """장면은 시장마다 한 번만 돌린다(두 시험이 같이 씀)."""
    if market not in _CACHE:
        _CACHE[market] = gs.run_market(market)
    return _CACHE[market]


# ---------------- README 에 적은 값 ----------------

def readme_count() -> int:
    m = re.search(r"^\| 골든 파일 수 \| (\d+) \|", README.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, "tests/golden/README.md 에 '| 골든 파일 수 | N |' 줄이 없어요"
    return int(m.group(1))


def readme_versions() -> dict:
    """README '기준 환경' 표의 {꾸러미: 버전}."""
    text = README.read_text(encoding="utf-8")
    return dict(re.findall(r"^\| (python|numpy|pandas|ta|finance-datareader) \| ([0-9][0-9.]*) \|$", text, re.MULTILINE))


def current_versions() -> dict:
    out = {"python": platform.python_version()}
    for name in ("numpy", "pandas", "ta", "finance-datareader"):
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = "없음"
    return out


def version_note() -> str:
    """지금 환경이 골든을 만든 환경과 다르면 사람이 읽을 경고 한 덩어리(같으면 빈 글자)."""
    want, have = readme_versions(), current_versions()
    diff = [f"{k}: 골든 {want[k]} / 지금 {have.get(k)}" for k in want if have.get(k) != want[k]]
    if not diff:
        return ""
    return ("※ 지금 라이브러리 버전이 골든을 만든 버전과 달라요 → 운영 동작이 같아도 다르게 나올 수 있어요(거짓 경보).\n"
            "  골든을 다시 만들지 말고 requirements-h1.txt 버전으로 환경부터 맞춘 뒤 다시 돌려 보세요.\n  "
            + "\n  ".join(diff) + "\n\n")


# ---------------- 비교 ----------------

def _readable_diff(path, want: bytes, got: bytes, limit=40) -> str:
    try:
        a, b = want.decode("utf-8").splitlines(), got.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return f"--- {path}: 바이너리 내용이 다름 (골든 {len(want)}바이트, 지금 {len(got)}바이트)"
    lines = list(difflib.unified_diff(a, b, f"골든/{path}", f"지금/{path}", n=2, lineterm=""))
    if not lines:     # 줄 내용은 같고 줄바꿈·끝 공백만 다름
        return f"--- {path}: 글자는 같아 보이지만 바이트가 다름(줄바꿈·인코딩 확인)"
    more = f"\n    … (차이 {len(lines) - limit}줄 더)" if len(lines) > limit else ""
    return "\n".join("    " + x for x in lines[:limit]) + more


def compare(want: dict, got: dict, max_files=6) -> list[str]:
    """골든(want)과 지금 결과(got)를 비교해 사람이 읽을 문제 목록을 만든다(같으면 빈 목록)."""
    problems = []
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    if missing:
        problems.append("지금 결과에 없는 골든 파일 (예: 저장해야 할 상태를 저장하지 않음):\n    " + "\n    ".join(missing))
    if extra:
        problems.append("골든에 없는 새 파일 (예: 저장하지 않던 날 저장함, 또는 골든 파일이 checkout 에 빠짐):\n    "
                        + "\n    ".join(extra))
    changed = [p for p in sorted(set(want) & set(got)) if want[p] != got[p]]
    for p in changed[:max_files]:
        problems.append(f"내용이 다른 파일 {p}:\n" + _readable_diff(p, want[p], got[p]))
    if len(changed) > max_files:
        problems.append(f"… 내용이 다른 파일 {len(changed) - max_files}개 더: " + ", ".join(changed[max_files:]))
    return problems


# ---------------- git ----------------

def _git(*args):
    """저장소에서 git 을 돌려 결과(바이트)를 돌려준다. git 이 없거나 저장소가 아니면 None."""
    if shutil.which("git") is None:
        return None
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r


def _nul_paths(out: bytes) -> set:
    return {unicodedata.normalize("NFC", p.decode("utf-8")) for p in out.split(b"\0") if p}


# ---------------- 시험 ----------------

def test_골든_파일_수가_README_와_같고_git_이_무시하지_않는다():
    files = gs.read_dir(GOLDEN)          # README 를 뺀 {상대경로: bytes}
    n = readme_count()
    assert len(files) == n, (f"tests/golden 파일 {len(files)}개 ≠ README 의 {n}개 — checkout 에 골든 파일이 빠졌거나 "
                             "README 숫자를 고치지 않았어요")
    for m in MARKETS:
        assert any(k.startswith(f"{m}/") and "/state/" in k for k in files), f"{m} 골든에 state 파일이 하나도 없어요"
    r = _git("rev-parse", "--is-inside-work-tree")
    if r is None or r.returncode != 0:
        pytest.skip("git 이 없거나 git 저장소가 아니라 git 부분은 건너뜀")
    rel = [f"tests/golden/{k}" for k in files] + ["tests/golden/README.md"]
    ig = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--no-index", "-z", "--stdin"],
                        input=b"\0".join(p.encode("utf-8") for p in rel) + b"\0", capture_output=True, timeout=60)
    assert ig.returncode in (0, 1), ig.stderr.decode("utf-8", "replace")      # 1 = 무시되는 것 없음
    ignored = _nul_paths(ig.stdout)
    assert not ignored, ("git 이 무시하는 골든 파일이 있어요(.gitignore 예외 확인, 2a 검토 A-1):\n  "
                         + "\n  ".join(sorted(ignored)[:10]))
    # `git add -A tests/golden` 뒤 커밋에 들어갈 파일 = (추적 중 + 추적되지 않았지만 무시도 안 되는 것) − 지운 것
    ls = _git("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "tests/golden")
    gone = _git("ls-files", "-z", "--deleted", "--", "tests/golden")
    listed = _nul_paths(ls.stdout) - _nul_paths(gone.stdout) - {"tests/golden/README.md"}
    assert len(listed) == n and listed == {f"tests/golden/{k}" for k in files}, (
        f"git ls-files 로 본 골든 파일 {len(listed)}개 ≠ README 의 {n}개")


@pytest.mark.parametrize("market", MARKETS)
def test_골든과_바이트까지_같다(market):
    want = {k: v for k, v in gs.read_dir(GOLDEN).items() if k.startswith(market + "/")}
    assert want, f"골든에 {market} 파일이 없어요"
    got, _ = _run(market)
    problems = compare(want, got)
    assert not problems, (version_note() + f"[{market}] 운영 동작이 골든(847ad13)과 달라졌어요. "
                          "의도한 변경이 아니면 코드를 되돌리세요.\n\n" + "\n\n".join(problems))


@pytest.mark.parametrize("market", MARKETS)
def test_장면이_가지를_지난다(market):
    _, info = _run(market)
    problems = gs.check_branches(market, info)
    assert not problems, version_note() + "\n".join(problems)


def test_비교_함수가_차이를_보여_준다():
    """compare 가 빠진 파일·새 파일·내용 차이를 모두 알려 주는지(시험의 시험)."""
    want = {"us/a/stdout.txt": "가\n나\n".encode(), "us/a/state/x.json": b"1", "us/b/stdout.txt": b"z"}
    got = {"us/a/stdout.txt": "가\n다\n".encode(), "us/a/state/x.json": b"1", "us/c/stdout.txt": b"z"}
    msg = "\n".join(compare(want, got))
    assert "us/b/stdout.txt" in msg and "us/c/stdout.txt" in msg
    assert "-나" in msg and "+다" in msg
    assert compare(want, dict(want)) == []


def test_버전이_다르면_경고를_만든다(monkeypatch):
    """README 기준 버전과 지금 버전이 다르면 version_note 가 무엇이 다른지 알려 준다(실패를 건너뛰지는 않음)."""
    want = readme_versions()
    assert set(want) == {"python", "numpy", "pandas", "ta", "finance-datareader"}
    monkeypatch.setattr(sys.modules[__name__], "current_versions", lambda: {**want, "pandas": "2.2.9"})
    note = version_note()
    assert "pandas: 골든 " + want["pandas"] + " / 지금 2.2.9" in note and "거짓 경보" in note
    monkeypatch.setattr(sys.modules[__name__], "current_versions", lambda: dict(want))
    assert version_note() == ""


def test_README_기준_버전은_requirements_h1_과_같다():
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([0-9][0-9.]*)", (ROOT / "requirements-h1.txt").read_text(encoding="utf-8"),
                           re.MULTILINE))
    pins = {k.lower(): v for k, v in pins.items()}
    want = readme_versions()
    for name in ("numpy", "pandas", "ta", "finance-datareader"):
        assert pins.get(name) == want[name], (name, pins.get(name), want[name])
    assert f"파이썬: {want['python']}" in (ROOT / "requirements-h1.txt").read_text(encoding="utf-8")
