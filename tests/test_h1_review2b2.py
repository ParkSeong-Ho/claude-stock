"""H1 단계 2b-2 독립 검토(docs/h1-review-2b2.md) C-1~C-18 고침 시험. 인터넷·claude 없음.

- C-1  환경 문제(디스크 가득·출력 막힘·메모리)는 L 이 아님 → 4·ENV, errors.jsonl 없음 / Ctrl-C → 130 / 코드 버그만 2
- C-2·C-9·C-16  분할: 두 번 적용 거절, 효력일 ≤ last_date 거절, D6 이 같은 비율의 분할 모양일 때만, 분수 r(1/3·3:1),
                밀린 봉이 있을 때(효력일 > last+1) 적용 뒤 처리한 봉은 나누지 않음(applied_after 기준)
- C-3  장부를 읽기 전 L24·관문 거절에도 start_date(없으면 "unknown" → status 가 지금 창으로 셈)
- C-4  종목군 절반 넘게 못 받으면 D2(start 도), 확인용 대형주 실패는 D7 판단 못 함을 분명히
- C-5  (tests/test_h1_runner.py test_C5_*, test_T_GATE_*) 통과 기록은 record_replay_pass 로만, 줄거나 바뀌면 3
- C-6  restart: 의도 줄 → 옮김 → 끝 줄, 중간에 꺼지면 다음 restart·start 가 마저(횟수 한 번)
- C-7  corp-action·amend-rules 가 커밋 뒤 일지 전에 꺼짐 → 다음 명령이 장부·meta 에서 일지를 채움
- C-8  start 는 지금 ≥ next_open(S) 이면 거절(8)
- C-10 정정 확정은 분할 모양 차이를 거절
- C-11 corp-action 도 관문·meta.rules 확인
- C-12 D4·D5 안내에 ⑦-3
- C-13 보유·대기 종목 t 종가, 대기 자산 시가·종가가 0 이하·NaN → D3
- C-14 F_FULLFSYNC(있으면)·새 폴더 fsync
- C-15 인자 오류 9, cli 는 모든 예외를 잡음
- C-17 밀린 봉 5개는 처리(6개는 6), start D7 거절, 대기 자산·매수 체결가 D6, 미국 16:14/16:16 ET, last_date≠HEAD → L24
- C-18 연도 경계를 실제 KRX 휴장(12-31·01-01)을 뺀 달력으로
"""
import errno
import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyst          # noqa: E402
import h1               # noqa: E402
import h1_check         # noqa: E402
import h1_fake_source as fs   # noqa: E402
import h1_synth as hs   # noqa: E402
import test_h1_runner as R    # noqa: E402

KST, ET = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")


class Crash(BaseException):
    """전원이 꺼진 것처럼 명령을 끊는다."""


@pytest.fixture(autouse=True)
def guards(monkeypatch):
    import h1_repo_guard as rg                                   # 저장소 state/·results/ 앞뒤 비교(단계 3 검토 T-3)
    repo_before = rg.snapshot(ROOT)

    def boom(*a, **k):
        raise AssertionError("시험이 진짜 claude 를 부르려 했어요")
    monkeypatch.setattr(analyst, "analyze_logged", boom)
    monkeypatch.setattr(analyst, "analyze", boom)
    monkeypatch.setattr(analyst, "claude_cli_version", boom)
    real_run = subprocess.run

    def guarded(args, *a, **k):
        if isinstance(args, (list, tuple)) and args and str(args[0]).endswith("claude"):
            raise AssertionError("시험이 claude 프로세스를 띄우려 했어요")
        return real_run(args, *a, **k)
    monkeypatch.setattr(subprocess, "run", guarded)

    def no_wait(s):
        raise AssertionError("잠금이 실제로 기다리려 했어요")
    monkeypatch.setattr(h1, "_lock_sleep", no_wait)
    yield
    moved = rg.changes(repo_before, rg.snapshot(ROOT))
    assert not moved, "시험이 저장소 state/·results/ 를 건드렸어요(이미 있던 맥 장부 포함): " + "; ".join(moved[:5])


def d_codes(h):
    return [p["code"] for p in h.ends()[-1]["problems"] if p["level"] == "D"]


def d_detail(h, code):
    return [p for p in h.ends()[-1]["problems"] if p["code"] == code][0]["detail"]


def crash_on(mp, pred):
    real = os.replace

    def fake(src, dst, *a, **k):
        if pred(Path(dst)):
            raise Crash(str(dst))
        return real(src, dst, *a, **k)
    mp.setattr(h1.os, "replace", fake)


def status_text(h):
    return "\n".join(h1.status(h.mk, h.root))


# ============================ C-1 환경 문제 · Ctrl-C ============================

def test_C1_디스크_가득은_ENV_4_L_아님_다음_실행이_되살림(tmp_path, monkeypatch):
    h = R.us_h(tmp_path, upto=2)
    real = h1._write_fsync

    def full(p, data):
        if p.name.startswith("HEAD.json"):                         # 장부 6개는 바꾼 뒤 HEAD 를 쓰다가 디스크 가득
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(p, data)
    monkeypatch.setattr(h1, "_write_fsync", full)
    assert h.run(h.D[3]) == 4
    assert d_codes(h) == ["ENV"] and "No space left" in d_detail(h, "ENV")
    assert not (h.root / "errors.jsonl").exists()                 # 재시작 사유(L)로 남기지 않음
    monkeypatch.setattr(h1, "_write_fsync", real)
    assert h.run(h.D[3]) == 0 and h.ends()[-1]["restored_from_backup"]
    text = status_text(h)
    assert "L 오류 0" in text and "자료 멈춤 1 (ENV 1)" in text


def test_C1_출력이_막혀도_명령은_그대로(tmp_path, monkeypatch):
    h = R.us_h(tmp_path, upto=1)

    def broken(*a, **k):
        raise BrokenPipeError(errno.EPIPE, "Broken pipe")
    monkeypatch.setattr("builtins.print", broken)
    assert h.run(h.D[2]) == 0 and h.last() == h.D[2]


@pytest.mark.parametrize("exc, code", [(MemoryError(), 4), (PermissionError(errno.EACCES, "권한 없음"), 4),
                                       (KeyboardInterrupt(), 130), (RuntimeError("버그"), 2)])
def test_C1_예외_분류(tmp_path, monkeypatch, exc, code):
    h = R.us_h(tmp_path, upto=1)
    snap = h.snap()
    real = h1.run_bar

    def raise_it(*a, **k):
        raise exc
    monkeypatch.setattr(h1, "run_bar", raise_it)
    assert h.run(h.D[2]) == code and h.snap() == snap
    assert h.ends()[-1]["exit_code"] == code
    assert (h.root / "errors.jsonl").exists() is (code == 2)      # 코드 버그만 errors.jsonl(L)
    monkeypatch.setattr(h1, "run_bar", real)
    assert h.run(h.D[2]) == 0


def test_C1_C15_cli_는_모든_예외를_잡음(tmp_path, monkeypatch):
    monkeypatch.setattr(h1, "H1_DIR", tmp_path / "h1")
    for exc, code in ((OSError(errno.EIO, "입출력 오류"), 4), (KeyboardInterrupt(), 130), (RuntimeError("버그"), 2)):
        def raise_it(*a, _e=exc, **k):
            raise _e
        monkeypatch.setattr(h1, "run", raise_it)
        assert h1.cli(["run", "--market", "us"]) == code
    assert h1.cli(["corp-action", "--market", "us", "--code", "AAA", "--source", "x"]) == 9   # 셋 중 하나도 없음
    assert h1.EXIT_USAGE == 9 and 1 not in (h1.EXIT_USAGE, h1.EXIT_INTERRUPT)


# ============================ C-2·C-9·C-16 분할 ============================

def test_C2_같은_분할을_두_번_치면_거절(tmp_path):
    h = R.us_h(tmp_path, upto=4)
    t = h.D[5]
    h.src.transform["BBB"] = fs.split_after(t, 2, ET)
    assert h.run(t) == 4
    before = {k: v["positions"]["BBB"]["shares"] for k, v in
              ((f"{a}/{tn}", h.states()[a][tn]) for a in h1.ARMS for tn in h1.TRAINERS) if "BBB" in v["positions"]}
    assert h.corp("BBB", split=2, date=t) == 0
    snap = h.snap()
    assert h.corp("BBB", split=2, date=t) == 9                     # 다시 쳐도 ×r² 가 되지 않음
    assert "이미 적용" in h.ends()[-1]["message"] and h.snap() == snap
    after = {k: v["positions"]["BBB"]["shares"] for k, v in
             ((f"{a}/{tn}", h.states()[a][tn]) for a in h1.ARMS for tn in h1.TRAINERS) if "BBB" in v["positions"]}
    assert after == {k: 2 * v for k, v in before.items()}
    assert h.run(t) == 0


def test_C2_C9_효력일이_last_date_이하면_거절(tmp_path):
    h = R.us_h(tmp_path, upto=4)
    h.src.transform["BBB"] = fs.split_after(h.D[5], 2, ET)
    assert h.run(h.D[5]) == 4
    snap = h.snap()
    for d in (h.D[4], h.D[3]):                                     # 신주배정 기준일처럼 이미 처리한 날을 넣음
        assert h.corp("BBB", split=2, date=d) == 9
        msg = h.ends()[-1]["message"]
        assert "새 주식 수로 거래되는 첫 날" in msg and "⑦-3 재시작 또는" in msg and "정정 확정" in msg
    assert h.snap() == snap


def test_C2_D6_이_분할_모양을_보지_않으면_거절_비율이_다르면_거절(tmp_path):
    h = R.us_h(tmp_path, upto=4)
    snap = h.snap()
    h.src.at(h.D[5])
    assert h.corp("BBB", split=2, date=h.D[5]) == 9                # 제공처가 아직 안 고침
    assert "분할 모양으로 보지 않아요" in h.ends()[-1]["message"]
    h.src.transform["BBB"] = fs.split_after(h.D[5], 2, ET)
    assert h.corp("BBB", split=3, date=h.D[5]) == 9                # 1차 출처 비율 착오
    assert "≠ --split" in h.ends()[-1]["message"]
    assert h.corp("BBB", split="2:1", date=h.D[5]) == 0            # 새 2 : 옛 1
    assert h.snap() != snap and h.run(h.D[5]) == 0


def test_C16_분수_비율():
    assert h1.parse_ratio("1/3") == Fraction(1, 3) and h1.parse_ratio("3:1") == 3
    assert h1.parse_ratio("1:3") == Fraction(1, 3) and h1.parse_ratio("0.5") == Fraction(1, 2)
    assert h1.parse_ratio(2) == 2 and h1.parse_ratio(2.0) == 2 and h1.parse_ratio(" 5 ") == 5
    for bad in ("a", "1", 1, "0", "-2", "1:0", "", None, True, float("nan")):
        with pytest.raises(ValueError):
            h1.parse_ratio(bad)


def test_C16_역병합_1대3_은_정확한_정수_확인(tmp_path):
    h = R.us_h(tmp_path, upto=4)
    t = h.D[5]
    h.src.transform["BBB"] = fs.split_after(t, 1 / 3, ET)         # 3주 → 1주(제공처가 지난 값을 ×3)
    assert h.run(t) == 4
    shares = sorted({h.states()[a][tn]["positions"]["BBB"]["shares"] for a in h1.ARMS for tn in h1.TRAINERS
                     if "BBB" in h.states()[a][tn]["positions"]})
    want = 0 if all(s % 3 == 0 for s in shares) else 9
    assert h.corp("BBB", split="1/3", date=t) == want              # 3 의 배수가 아닌 보유가 있으면 ⑦-3
    if want:
        assert "정수가 아님" in h.ends()[-1]["message"]


def test_C2_밀린_봉이_있을_때_분할_적용_뒤_처리한_봉은_나누지_않음(tmp_path):
    h = R.us_h(tmp_path, upto=4)                                   # last = D4, 효력일 D6 (D5 는 아직 처리 안 함)
    h.src.transform["BBB"] = fs.split_after(h.D[6], 2, ET)
    assert h.run(h.D[6]) == 4 and "분할 의심(비율 r=2)" in d_detail(h, "D6")
    assert h.corp("BBB", split=2, date=h.D[6]) == 0
    assert h.run(h.D[6]) == 0 and h.ends()[-1]["bars"] == [h.D[5], h.D[6]]   # D5 는 고쳐진 시세로 처리됨
    assert h.run(h.D[7]) == 0                                      # D5 marks 를 ÷2 하지 않으므로 거짓 D6 없음
    assert h1_check.errors(h.recheck(R.allowed_now())) == []


def test_C2_C7_커밋_뒤_일지_전에_꺼지면_다시_쳐도_두_번_적용_안되고_일지는_채워짐(tmp_path, monkeypatch):
    h = R.us_h(tmp_path, upto=4)
    t = h.D[5]
    h.src.transform["BBB"] = fs.split_after(t, 2, ET)
    assert h.run(t) == 4
    real = h1._append_line

    def cut(path, rec):
        if path.name == "corp_actions.jsonl":
            raise Crash("일지 쓰기 전")
        return real(path, rec)
    with monkeypatch.context() as mp:
        mp.setattr(h1, "_append_line", cut)
        with pytest.raises(Crash):
            h.corp("BBB", split=2, date=t)
    assert h.states()["A0"]["마라토너"]["corp_actions"][-1]["kind"] == "split"   # 장부(원본)에는 반영됨
    assert not (h.mdir / "corp_actions.jsonl").exists()
    assert h.corp("BBB", split=2, date=t) == 9                     # 다시 쳐도 거절(이미 적용)
    ca = fs.read_lines(h.mdir / "corp_actions.jsonl")
    ch = [r for r in fs.read_lines(h.root / "changes.jsonl") if r["kind"] == "corp-action:split"]
    assert len(ca) == 1 and ca[0]["recovered"] is True and ca[0]["r"] == 2.0
    assert len(ch) == 1 and ch[0]["recovered"] is True
    assert h.run(t) == 0
    assert len(fs.read_lines(h.mdir / "corp_actions.jsonl")) == 1  # 한 번만 채움


# ============================ C-3 start_date ============================

def test_C3_장부를_읽기_전_L24_도_창_S_로_기록(tmp_path):
    h = R.us_h(tmp_path, upto=2)
    p = h.mdir / "A1" / "team_스프린터.json"
    orig = p.read_bytes()
    p.write_bytes(orig + b" ")
    assert h.run(h.D[3]) == 2
    assert h.errors()[-1]["start_date"] == hs.S_A and h.ends()[-1]["start_date"] == hs.S_A
    p.write_bytes(orig)
    assert "L 오류 1" in status_text(h)


def test_C3_S_를_못_읽으면_unknown_이고_status_는_지금_창으로_셈(tmp_path):
    h = R.us_h(tmp_path, upto=2)
    files = [h.mdir / "meta.json", h.mdir / "A0" / "team_마라토너.json"]
    orig = [f.read_bytes() for f in files]
    for f in files:
        f.write_bytes(b"{")
    assert h.run(h.D[3]) == 2
    assert h.errors()[-1]["start_date"] == "unknown" and h.ends()[-1]["start_date"] == "unknown"
    for f, b in zip(files, orig):
        f.write_bytes(b)
    assert "L 오류 1" in status_text(h)                            # 보수적으로 지금 창에 셈
    assert h1._in_window({"start_date": "unknown", "at": "2026-01-01T00:00:00+09:00"}, hs.S_A,
                         "2026-02-03T07:10:00+09:00") is False     # 창이 만들어지기 전 기록은 빼고
    assert h1._in_window({"start_date": None, "at": "엉망"}, hs.S_A, "2026-02-03T07:10:00+09:00") is True


# ============================ C-4 종목군 대량 실패 ============================

def test_C4_종목군을_대부분_못_받으면_start_는_4(tmp_path):
    h = R.us_h(tmp_path)
    h.src.missing = set(R.US_CODES)
    assert h.start() == 4 and d_codes(h) == ["D2"]
    assert "절반 넘음" in d_detail(h, "D2") and not h.mdir.exists()
    h.src.missing = set()
    assert h.start() == 0


def test_C4_비율_경계와_상장폐지_종목(tmp_path):
    class L:
        problems, extra = [], {}
    codes = [f"C{i}" for i in range(10)]
    ok = object()
    fetched = {c: ok for c in codes}
    for c in codes[:5]:
        fetched[c] = None
    h1._universe_check("us", codes, fetched, set(), set(), L)      # 5/10 = 절반 → W4 만
    assert [p.code for p in L.problems] == ["W4"] * 5
    fetched["C5"] = None
    with pytest.raises(h1.H1DataProblem) as e:                     # 6/10 > 절반 → D2
        h1._universe_check("us", codes, fetched, set(), set(), L)
    assert e.value.kind == "D2"
    L.problems = []
    h1._universe_check("us", codes, fetched, set(), {"C0", "C1"}, L)   # 상장폐지 등록 종목은 비율에서 뺌(4/8)
    assert len(L.problems) == 6                                    # W4 로는 남김(상장폐지 종목 포함)
    L.problems = []
    h1._universe_check("us", codes, fetched, {"C2", "C3"}, {"C0", "C1"}, L)
    assert len(L.problems) == 4                                    # 보유·대기 종목(need)은 W4 가 아님(D2 몫)


def test_C4_run_도_종목군_대량_실패면_4(tmp_path):
    h = R.us_h(tmp_path, upto=1)
    need = {c for a in h1.ARMS for tn in h1.TRAINERS
            for c in set(h.states()[a][tn]["positions"]) | {o["code"] for o in h.states()[a][tn]["pending"]}}
    only = [c for c in R.US_CODES if c not in need]
    h.src.missing = set(only)
    if len(only) > len(R.US_CODES) / 2:
        assert h.run(h.D[2]) == 4 and d_codes(h) == ["D2"]
    else:
        pytest.skip("이 장면은 종목군에만 있는 종목이 절반 이하")


def test_C4_확인용_대형주를_못_받으면_D7_판단_못_함을_기록(tmp_path):
    h = R.us_h(tmp_path, upto=1)
    h.src.missing = {"AAPL", "MSFT"}
    assert h.run(h.D[2]) == 0
    end = h.ends()[-1]
    assert end["d7_checked"] is False and any("판단하지 못했어요" in n for n in end["notes"])
    h.src.missing = {"AAPL"}
    assert h.run(h.D[3]) == 0
    assert h.ends()[-1]["d7_checked"] is True and any("남은 종목으로만" in n for n in h.ends()[-1]["notes"])


# ============================ C-6 restart 기록 순서 ============================

def test_C6_옮기기_전에_꺼지면_다음_restart_가_마저(tmp_path, monkeypatch):
    h = R.us_h(tmp_path, upto=1)
    with monkeypatch.context() as mp:
        crash_on(mp, lambda dst: dst.parent.name == "archive")
        with pytest.raises(Crash):
            R._restart(h, "첫 이유")
    rs = fs.read_lines(h.root / "restarts.jsonl")
    assert [r["status"] for r in rs] == ["moving"] and h.mdir.is_dir()
    assert h.start() == 8 and "restart 를 다시" in h.ends()[-1]["message"]
    dest = h1.restart("us", "L", h.root, confirm="us", note="다른 이유여도 됨")   # 새 재시작이 아니라 남은 이동을 끝냄
    assert dest.name == Path(rs[0]["archive"]).name and dest.is_dir() and not h.mdir.exists()
    assert h1.restart_info("us", h.root)["used"] == 1
    assert h.start() == 0 and h.meta()["restart_no"] == 1


def test_C6_옮긴_뒤_끝_줄_전에_꺼지면_start_가_마저(tmp_path, monkeypatch):
    h = R.us_h(tmp_path, upto=1)
    real = h1._append_log

    def cut(root, name, rec):
        if name == "restarts.jsonl" and rec.get("status") == "done":
            raise Crash("끝 줄 전")
        return real(root, name, rec)
    with monkeypatch.context() as mp:
        mp.setattr(h1, "_append_log", cut)
        with pytest.raises(Crash):
            R._restart(h, "이유")
    assert not h.mdir.exists()
    assert h.start() == 0                                          # 흔적만 있는데 재시작 기록 없음 → 8 이 아님
    rs = fs.read_lines(h.root / "restarts.jsonl")
    assert [r["status"] for r in rs] == ["moving", "done"] and rs[1].get("recovered") is True
    assert h1.restart_info("us", h.root, h.meta())["used"] == 1 and h.meta()["restart_no"] == 1


# ============================ C-7 amend-rules 일지 ============================

def test_C7_amend_rules_커밋_전후에_꺼짐(tmp_path, monkeypatch):
    base = tuple(h1.KR_SELL_TAX)
    h = R.kr_h(tmp_path, upto=2)
    monkeypatch.setattr(h1, "KR_SELL_TAX", base + (("2027-01-01", 0.0015),))
    with monkeypatch.context() as mp:                              # 커밋(HEAD) 전에 꺼짐
        crash_on(mp, lambda dst: dst.name == "HEAD.json")
        with pytest.raises(Crash):
            h1.amend_rules("kr", "https://law.go.kr/1", h.root, gate=False)
    assert h.run(h.D[3]) == 3                                      # 규칙 다름(커밋 안 됨) — 그래도 일지는 맞춤
    st = [r["status"] for r in fs.read_lines(h.root / "changes.jsonl") if r["kind"] == "amend-rules"]
    assert st == ["pending", "abandoned"]
    real = h1._append_log

    def cut(root, name, rec):
        if name == "changes.jsonl" and rec.get("status") == "done" and not rec.get("recovered"):
            raise Crash("done 전")
        return real(root, name, rec)
    with monkeypatch.context() as mp:                              # 커밋 뒤 done 전에 꺼짐
        mp.setattr(h1, "_append_log", cut)
        with pytest.raises(Crash):
            h1.amend_rules("kr", "https://law.go.kr/2", h.root, gate=False)
    assert h.run(h.D[3]) == 0                                      # 커밋은 됐음 → 정상 + 일지 채움
    lines = [r for r in fs.read_lines(h.root / "changes.jsonl") if r["kind"] == "amend-rules"]
    assert [r["status"] for r in lines] == ["pending", "abandoned", "pending", "done"]
    assert lines[-1]["recovered"] is True and lines[-1]["source"] == "https://law.go.kr/2"


# ============================ C-8 start 시각 ============================

@pytest.mark.parametrize("mk, when, code", [
    ("kr", (10, 0), 8), ("kr", (20, 0), 8), ("kr", (23, 5), 0), ("us", (9, 31), 8), ("us", (7, 10), 0)])
def test_C8_S_봉이_늦은_봉이_되는_start_는_거절(tmp_path, mk, when, code):
    h = R.kr_h(tmp_path) if mk == "kr" else R.us_h(tmp_path)
    if mk == "kr":                                                 # 다음날 10:00·20:00 → S = 그 전날, 이미 장이 열림
        d = pd.Timestamp(h.D[1] if when[0] < 23 else h.D[0])
        clock = datetime(d.year, d.month, d.day, *when, tzinfo=KST)
    else:                                                          # 미국: S 다음 평일 09:31 ET 는 장이 열린 뒤
        d = pd.Timestamp(h.D[1])
        clock = datetime(d.year, d.month, d.day, 9, 31, tzinfo=ET) if when == (9, 31) else fs.run_at("us", h.D[0])
    assert h.start(clock=clock) == code
    if code:
        assert "늦은 봉" in h.ends()[-1]["message"] and not h.mdir.exists()
    else:
        assert h.states()["A0"]["마라토너"]["days"][0]["mode"] == "llm"


# ============================ C-10·C-11 ============================

def test_C10_정정_확정은_분할_모양을_거절(tmp_path):
    h = R.us_h(tmp_path, upto=4)
    h.src.transform["BBB"] = fs.split_after("2026-01-01", 2, ET)
    h.src.at(h.D[5])
    snap = h.snap()
    assert h.corp("BBB", accept_correction=True) == 9
    assert "--split 2" in h.ends()[-1]["message"] and h.snap() == snap
    h.src.transform.clear()
    h.src.idle_raw = h.src.idle_raw.copy()
    for col in ("Open", "High", "Low", "Close"):
        h.src.idle_raw[col] = h.src.idle_raw[col] * 1.5            # 지수 전체 기준이 바뀜
    assert h.corp("SPY", accept_correction=True) == 9 and "⑦-3" in h.ends()[-1]["message"]


def test_C11_corp_action_도_관문과_규칙_확인(tmp_path, monkeypatch):
    h = R.us_h(tmp_path, upto=3)
    snap = h.snap()
    assert h.corp("CCC", delist=True, last_date=h.D[3], gate=True) == 3     # replay_pass 없음
    real = h1.MAX_LATE_TOTAL
    monkeypatch.setattr(h1, "MAX_LATE_TOTAL", 11)
    assert h.corp("CCC", delist=True, last_date=h.D[3]) == 3               # meta.rules 다름
    assert h.snap() == snap
    monkeypatch.setattr(h1, "MAX_LATE_TOTAL", real)
    R._pass(h.root, None, h1.env_info())
    h.at(h.D[4]).src.missing.add("CCC")                                  # 다음 거래일이 지났고 그 종목만 시세 없음(F-3)
    assert h.corp("CCC", delist=True, last_date=h.D[3], gate=True) == 0


# ============================ C-12·C-13 ============================

def test_C12_D4_D5_안내에_7_3(tmp_path):
    h = R.us_h(tmp_path, upto=4)
    h.src.idle_drop = {h.D[2]}
    assert h.run(h.D[5]) == 4 and "⑦-3 재시작" in d_detail(h, "D4")
    h.src.idle_drop = {h.D[5]}
    assert h.run(h.D[6]) == 4 and "⑦-3 재시작" in d_detail(h, "D5")


@pytest.mark.parametrize("bad", [0.0, -5.0, float("inf")])
def test_C13_보유_종목_t_종가가_이상하면_D3(tmp_path, bad):
    h = R.us_h(tmp_path, upto=3)
    t = h.D[4]

    def f(df, now):
        if pd.Timestamp(t) in df.index:
            df.loc[pd.Timestamp(t), "Close"] = bad
        return df
    h.src.transform["BBB"] = f
    snap = h.snap()
    assert h.run(t) == 4 and d_codes(h) == ["D3"] and h.snap() == snap
    h.src.transform.clear()
    assert h.run(t) == 0


@pytest.mark.parametrize("col, bad", [("Open", 0.0), ("Close", -1.0), ("Open", float("inf"))])
def test_C13_대기_자산_시가_종가가_이상하면_D3(tmp_path, col, bad):
    h = R.us_h(tmp_path, upto=3)
    t = h.D[4]
    good = h.src.idle_raw.copy()
    h.src.idle_raw = good.copy()
    h.src.idle_raw.loc[pd.Timestamp(t), col] = bad
    assert h.run(t) == 4 and d_codes(h) == ["D3"]
    h.src.idle_raw = good
    assert h.run(t) == 0


# ============================ C-14 디스크 쓰기 ============================

def test_C14_F_FULLFSYNC_가_있으면_쓴다(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(fcntl, "F_FULLFSYNC", 51, raising=False)
    monkeypatch.setattr(fcntl, "fcntl", lambda fd, op, *a: calls.append(op) or 0)
    log = h1.DecisionLog(tmp_path / "h1" / "analyst_cache.jsonl")
    log.append([{"key": "a"}])
    assert calls.count(51) >= 1                                    # 판정 기록 줄
    n = len(calls)
    h1._write_fsync(tmp_path / "x" / "y.json", b"{}")
    assert calls.count(51) > n                                     # 파일·새 폴더


def test_C14_새_폴더는_부모를_fsync(tmp_path, monkeypatch):
    seen = []
    real = h1._fsync_dir
    monkeypatch.setattr(h1, "_fsync_dir", lambda d: (seen.append(Path(d)), real(d))[1])
    h1._mkdirs(tmp_path / "a" / "b" / "c")
    assert seen == [tmp_path, tmp_path / "a", tmp_path / "a" / "b"]
    h = R.us_h(tmp_path, upto=1)
    seen.clear()
    assert h.run(h.D[2]) == 0
    names = {(p.parent.name, p.name) for p in seen}
    assert any(par.endswith(".tmp") and n == "A0" for par, n in names)   # 백업 임시 폴더 안 새 하위 폴더
    assert ("us", "backup") in names                               # 백업 이름 바꾼 뒤 부모


# ============================ C-17 시험 빈틈 ============================

def test_C17_밀린_봉_5개는_처리_6개는_6(tmp_path):
    h = R.us_h(tmp_path, upto=3)
    assert h.run(h.D[8]) == 0 and h.ends()[-1]["bars"] == h.D[4:9]  # 정확히 5봉
    assert h.ends()[-1]["late_bars"] == h.D[4:8]
    assert h.run(h.D[14]) == 6                                     # 6봉


def test_C17_start_D7_거절(tmp_path):
    h = R.kr_h(tmp_path)
    h.src.idle_until = h.w.prev(h.S)                                # KS200 에 S 봉이 아직 없음
    d = pd.Timestamp(h.S)
    assert h.start(clock=datetime(d.year, d.month, d.day, 22, 31, tzinfo=KST)) == 7
    assert d_codes(h) == ["D7"] and not h.mdir.exists()


def test_C17_대기_자산_지난_시가가_바뀌면_D6(tmp_path):
    h = R.us_h(tmp_path, upto=4)
    h.src.idle_raw = h.src.idle_raw.copy()
    h.src.idle_raw.loc[pd.Timestamp(h.D[3]), "Open"] *= 1.001
    assert h.run(h.D[5]) == 4 and "SPY" in d_detail(h, "D6") and "대기 자산 시가" in d_detail(h, "D6")


def test_C17_오래_보유한_종목의_매수일_시가만_바뀌어도_D6(tmp_path):
    h = R.us_h(tmp_path, upto=8)                                   # BBB 는 D1 매수 → 최근 5일 marks 밖
    st = h.states()["A0"]["마라토너"]
    assert st["positions"]["BBB"]["buy_date"] == h.D[1] and h.D[1] not in [r["date"] for r in st["days"][-5:]]

    def f(df, now):
        df.loc[pd.Timestamp(h.D[1]), "Open"] *= 1.001
        return df
    h.src.transform["BBB"] = f
    assert h.run(h.D[9]) == 4 and "매수 체결가" in d_detail(h, "D6")


def test_C17_미국_16시15분_ET_경계(tmp_path):
    h = R.us_h(tmp_path, upto=3)
    h.src.idle_until = h.D[3]                                      # SPY 는 D4 봉이 없음
    d = pd.Timestamp(h.D[4])
    assert h.run(clock=datetime(d.year, d.month, d.day, 16, 14, tzinfo=ET)) == 0   # 대형주 D4 도 아직 확정 전
    assert h.run(clock=datetime(d.year, d.month, d.day, 16, 16, tzinfo=ET)) == 7   # 대형주 D4 확정, SPY 없음
    assert h.last() == h.D[3]
    assert h1._settle_time("us", h.D[4]) == datetime(d.year, d.month, d.day, 16, 15, tzinfo=ET)
    assert h1._settle_time("kr", h.D[4]).hour == 22 and h1._settle_time("kr", h.D[4]).minute == 30


def test_C17_장부_last_date_가_HEAD_와_다르면_L24(tmp_path):
    h = R.us_h(tmp_path, upto=3)
    rel = "A1/team_파이오니어.json"
    p = h.mdir / rel
    d = json.loads(p.read_text(encoding="utf-8"))
    d["last_date"] = h.D[2]
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    head = h.head()
    head["files"][rel] = fs.file_sha(p)
    (h.mdir / "HEAD.json").write_text(json.dumps(head, ensure_ascii=False, indent=1), encoding="utf-8")
    assert h.run(h.D[4]) == 2
    err = h.errors()[-1]["problems"][-1]
    assert err["code"] == "L24" and "HEAD.last_date" in err["detail"]


# ============================ C-18 KRX 휴장일 연도 경계 ============================

def test_C18_연도_경계_KRX_휴장일을_뺀_달력(tmp_path):
    w = fs.drop_days(R.kr_world(start="2026-06-01", end="2027-02-26"), ["2026-12-25", "2026-12-31", "2027-01-01"])
    assert not {"2026-12-25", "2026-12-31", "2027-01-01"} & set(w.dates)   # KRX 휴장(성탄절·연말·신정)
    h = R.kr_h(tmp_path, world=w, S="2026-12-24", upto=3)          # 12-28·29·30 처리(12-25 휴장)
    assert h.last() == "2026-12-30"
    h.src.idle_until = "2026-12-30"                                # 2027.csv 가 아직 없음
    assert h.run(clock=datetime(2027, 1, 4, 23, 5, tzinfo=KST)) == 7 and h.last() == "2026-12-30"
    h.src.idle_until = None
    assert h.run(clock=datetime(2027, 1, 4, 23, 10, tzinfo=KST)) == 0 and h.last() == "2027-01-04"
    rows = [r["date"] for r in h.states()["A0"]["마라토너"]["days"]]
    assert rows[-2:] == ["2026-12-30", "2027-01-04"]               # 휴장일은 빠짐(빠진 날 아님)
    h.src.idle_from = "2027-01-01"                                 # 2026.csv 를 못 받음
    assert h.run(clock=datetime(2027, 1, 5, 23, 5, tzinfo=KST)) == 4 and d_codes(h) == ["D4"]
    h.src.idle_from = None
    assert h.run(clock=datetime(2027, 1, 5, 23, 5, tzinfo=KST)) == 0
    assert h1_check.errors(h.recheck(R.allowed_now())) == []


def test_C14_반쯤_쓴_일지_줄_뒤에는_새_줄로(tmp_path):
    p = tmp_path / "h1" / "runs.jsonl"
    p.parent.mkdir(parents=True)
    p.write_bytes(b'{"event":"start"}\n{"event":"en')             # 쓰는 중 꺼짐
    h1._append_line(p, {"event": "x"})
    assert [r["event"] for r in h1.read_jsonl(p)] == ["start", "x"]


def test_C17_D5_종목군_정확히_절반이_거래한_날도_구멍(tmp_path):
    h = R.us_h(tmp_path, upto=4)
    t = h.D[5]
    h.src.idle_drop = {t}                                          # SPY 에 t 가 없음
    for c in R.US_CODES[len(R.US_CODES) // 2:]:                   # t 를 아직 처리하지 않으므로 보유 종목도 빼도 됨
        h.src.drop[c] = {t}
    traded = sum(1 for c in R.US_CODES if t not in h.src.drop.get(c, ()))
    assert traded * 2 == len(R.US_CODES)                           # 정확히 절반이 t 에 거래
    assert h.run(h.D[6]) == 4 and d_codes(h) == ["D5"]


def test_C17_커밋_도중_남은_tmp_는_다음_실행이_치움(tmp_path):
    h = R.us_h(tmp_path, upto=2)
    junk = [h.mdir / "meta.json.tmp", h.mdir / "A1" / "team_스프린터.json.tmp"]
    for j in junk:
        j.write_bytes(b"{half")
    snap = {k: v for k, v in fs.tree_sha(h.mdir).items() if not k.endswith(".tmp")}
    assert h.run(h.D[2], hh=8) == 0                                # 같은 봉 다시(커밋 없음) — 정리만으로 지워져야 함
    assert not any(j.exists() for j in junk)
    assert {k: v for k, v in fs.tree_sha(h.mdir).items() if k != "calendar.jsonl"} == \
        {k: v for k, v in snap.items() if k != "calendar.jsonl"}
