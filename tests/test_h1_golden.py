"""T-GOLD (설계 docs/h1-forward-design.md §6, §7 R13) — 운영 동작이 '바꾸기 전'과 바이트까지 같은지.

- 골든 `tests/golden/` 은 코드를 고치기 전 커밋(847ad13)을 따로 꺼낸 git worktree 에서
  `tests/golden_scenarios.py` 로 만들었다(만든 날짜·명령·장면 목록은 tests/golden/README.md).
- 이 시험은 같은 장면을 **지금 코드**로 다시 돌려, 파일 목록과 내용(상태 JSON·화면 출력·팀장 호출·스크리너 결과)이
  골든과 바이트까지 같은지 본다. 다르면 어느 파일이 어떻게 다른지 읽기 쉽게 보여 준다.
- 장면이 정말 그 가지(서킷·정지·멱등·22:30 …)를 지나는지도 다시 확인한다.
- 인터넷·claude·키 없이 돈다(입출력 경계만 가짜로 바꿔 끼움, golden_scenarios.py 설명).
"""
import difflib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import golden_scenarios as gs   # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"
MARKETS = ("us", "kr")
_CACHE = {}


def _run(market):
    """장면은 시장마다 한 번만 돌린다(두 시험이 같이 씀)."""
    if market not in _CACHE:
        _CACHE[market] = gs.run_market(market)
    return _CACHE[market]


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
        problems.append("골든에 없는 새 파일 (예: 저장하지 않던 날 저장함):\n    " + "\n    ".join(extra))
    changed = [p for p in sorted(set(want) & set(got)) if want[p] != got[p]]
    for p in changed[:max_files]:
        problems.append(f"내용이 다른 파일 {p}:\n" + _readable_diff(p, want[p], got[p]))
    if len(changed) > max_files:
        problems.append(f"… 내용이 다른 파일 {len(changed) - max_files}개 더: " + ", ".join(changed[max_files:]))
    return problems


def test_골든_폴더가_있다():
    assert (GOLDEN / "README.md").exists()
    for m in MARKETS:
        assert (GOLDEN / m).is_dir(), f"tests/golden/{m} 없음"


@pytest.mark.parametrize("market", MARKETS)
def test_골든과_바이트까지_같다(market):
    want = {k: v for k, v in gs.read_dir(GOLDEN).items() if k.startswith(market + "/")}
    assert want, f"골든에 {market} 파일이 없어요"
    got, _ = _run(market)
    problems = compare(want, got)
    assert not problems, (f"[{market}] 운영 동작이 골든(847ad13)과 달라졌어요. "
                          "의도한 변경이 아니면 코드를 되돌리세요.\n\n" + "\n\n".join(problems))


@pytest.mark.parametrize("market", MARKETS)
def test_장면이_가지를_지난다(market):
    _, info = _run(market)
    problems = gs.check_branches(market, info)
    assert not problems, "\n".join(problems)


def test_비교_함수가_차이를_보여_준다():
    """compare 가 빠진 파일·새 파일·내용 차이를 모두 알려 주는지(시험의 시험)."""
    want = {"us/a/stdout.txt": "가\n나\n".encode(), "us/a/state/x.json": b"1", "us/b/stdout.txt": b"z"}
    got = {"us/a/stdout.txt": "가\n다\n".encode(), "us/a/state/x.json": b"1", "us/c/stdout.txt": b"z"}
    msg = "\n".join(compare(want, got))
    assert "us/b/stdout.txt" in msg and "us/c/stdout.txt" in msg
    assert "-나" in msg and "+다" in msg
    assert compare(want, dict(want)) == []
