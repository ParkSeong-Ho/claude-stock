"""H1 단계 2b-2 — 실행기 시험 (설계 docs/h1-forward-design.md §6). 인터넷·claude·키 없음.

장부 폴더는 tmp_path, 자료는 가짜 DataSource(tests/h1_fake_source.py), 시계는 시간대 있는 고정 시각.
진짜 claude 는 절대 부르지 않는다: analyst.analyze_logged·analyze·claude_cli_version 을 가짜로 바꿔 끼우고,
claude 프로세스를 띄우려 하면 실패하게 한다. 시험이 저장소 state/·results/ 를 건드리면(이미 있던 것 포함) 실패한다.

설계 §6 ID ↔ 시험
- T-F1a  test_T_F1a_*         경로 모양, H1 폴더 밖·운영 폴더 거절
- T-F1b  test_T_F1b_*         운영 장부 파일 지문·수정시각 그대로, team._load·_save·main.load_state_file 금지
- T-F4   test_T_F4_*          대기 자산 = 벤치마크, 국내 allow_index 경로·22:30, 시가·종가 = 그 시세
- T-FETCH test_T_FETCH_*      h1.fetch == main.load_prices, 국내 정지 날짜 = 원본 Volume=0
- T-D    test_T_D_*           D1~D7: 종료 코드 4/7, 그 봉 저장 안 함, errors·restarts 없음, 다음 실행 정상
- T-LATEDATA test_T_LATEDATA_* 실행 수준(첫 실행 D3 → 다음 실행 정상, 국내 Volume=0 은 정지로 진행)
- T-RETRO test_T_RETRO_*      분할 의심 r=2 → corp-action --split → 정상, 국내 정지일 marks 는 D6 안 남
- T-DELIST test_T_DELIST_*    시세를 못 받는 상태에서 등록 → 다음 run 진행, 같은 날 전량 정리·비용, L23
- T-CORR test_T_CORR_*        정정 확정
- T-AMEND test_T_AMEND_*      세율 줄 추가
- T-CAL  test_T_CAL_*         D4·22:29/22:31 D7·2026→2027 연도 파일
- T-CUT  test_T_CUT_*         국내 20:00 / 22:31 KST
- T-DST  test_T_DST_*         미국 서머타임 앞뒤 07:10 KST
- T-LATE test_T_LATE_*        2봉 밀림 → 차례로·late, 6봉 → 6
- T-LLMTIME test_T_LLMTIME_*  국내 08:59 vs 10:00 KST 실행
- T-GATE test_T_GATE_*        지문·env 다름 → 3, 파일 0개(runs.jsonl 만), meta.rules 다름 → 3
- T-LOCK test_T_LOCK_*        가짜 시계 30분 초과 → 5 (모든 명령)
- T-HEAD test_T_HEAD_*        3개 바꾼 뒤 멈춤 → 백업으로 되살려 같은 결과, corp-action 뒤, 둘 다 안 맞음 → L24·2
- T-STRICT test_T_STRICT_*    JSON 깨짐·NaN·형식 → 2, 새로 시작 안 함
- T-NEWSTART test_T_NEWSTART_* 명시 시작 규칙
- T-UNIV test_T_UNIV_*        종목군 고정
- T-F6a·b·c test_T_F6*        주문 실행기 격리
- T-F7   test_T_F7_*          같은 봉 두 번째 run → 파일 그대로, 팀장 0번, 봉마다 scan_frames 1번
- T-JSONL test_T_JSONL_*      HEAD 전에 꺼짐 → 남은 판정 줄 재사용(LLM 0번), 반쯤 쓴 줄 잘라냄
- 그 밖에    L 오류·L 예외 → errors.jsonl(지문), 예상 밖 예외 → 2(지문 없음), 사전 조건 → 4, claude --version 은
            실행마다 한 번(llm 일 때만), status 는 파일을 고치지 않음, cli 인자 오류 → 1
- 여러 날 끝까지 test_E2E_*    미국·국내 start → 15거래일 넘게(정지·분할·상장폐지·늦은 봉·늦은 자료) → 저장 파일만으로
                              check_ledger·check_pair L 0, 두 번 돌린 실행의 ledger_fingerprint 같음
"""
import ast
import fcntl
import json
import os
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
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
import main             # noqa: E402
import markets          # noqa: E402
import order_runner     # noqa: E402
import screener         # noqa: E402
import team             # noqa: E402
from broker.fake import FakeBroker   # noqa: E402

KST, ET = ZoneInfo("Asia/Seoul"), ZoneInfo("America/New_York")
CLI_VER = "9.9.9 (가짜)"


class Crash(BaseException):
    """전원이 꺼진 것처럼 명령을 중간에 끊는다(Exception 이 아니라 명령 안에서 잡히지 않음)."""


@pytest.fixture(autouse=True)
def guards(monkeypatch):
    """진짜 claude 금지 · 잠금에서 실제로 기다리지 않음 · 저장소 state/·results/ 를 건드리면 실패."""
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


# ============================ 시험 도우미 ============================

US_CODES = hs.CODES_A + ("AAPL", "MSFT")           # AAPL·MSFT = 미국 달력 확인용 대형주(CAL_PROBE)
KR_CODES = ("005930", "000660", "005380", "035420", "105560", "068270")
KR_BASES = {"005930": 70000, "000660": 150000, "005380": 200000, "035420": 180000, "105560": 60000, "068270": 170000}


def us_world(**kw):
    return hs.World("us", US_CODES, bases={"FFF": 2000.0}, **kw)


def kr_world(**kw):
    return hs.World("kr", KR_CODES, bases=KR_BASES, **kw)


def plan_kr(D):
    return {"마라토너": {"buy": [("005930", D[0]), ("000660", D[0])], "sell": [("005930", D[6])]},
            "스프린터": {"buy": [("005380", D[0]), ("035420", D[1])], "sell": [("035420", D[9])]},
            "파이오니어": {"buy": [("105560", D[2])]}}


class H:
    """장부 폴더 하나 + 가짜 자료 + 가짜 브레인·팀장으로 h1.start·h1.run 을 부르는 도우미."""

    def __init__(self, tmp_path, world, S, plan=None, ask=None, *, root=None, n_days=24, universe=None, name="h1",
                 default_root=False):
        self.root = Path(tmp_path) / name if root is None else Path(root)
        self.arg_root = None if default_root else self.root     # None = h1 기본 위치(H1_DIR)를 그대로 쓴다
        self.w, self.mk, self.S = world, world.market, S
        self.D = [world.at(S, k) for k in range(n_days)]
        self.src = fs.FakeSource(world, universe=universe)
        self.brains = hs.fake_brains(plan(self.D) if plan else {})
        self.ask = ask if ask is not None else hs.FakeAsk()

    def _call(self, fn, *a, **k):
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(team, "BRAINS", self.brains)
            mp.setattr(screener, "BRAINS", self.brains)
            mp.setattr(analyst, "analyze_logged", self.ask)
            mp.setattr(analyst, "claude_cli_version", lambda: CLI_VER)
            return fn(*a, **k)

    def at(self, t, hh=None, mm=None):
        self.src.at(t, hh=hh, mm=mm)
        return self

    def start(self, gate=False, clock=None, **kw):
        self.at(self.S)
        if clock is not None:
            self.src.clock = clock
        return self._call(h1.start, self.mk, self.arg_root, self.src, gate=gate, **kw)

    def run(self, t=None, gate=False, hh=None, mm=None, clock=None, **kw):
        if clock is not None:
            self.src.clock = clock
        elif t is not None:
            self.at(t, hh, mm)
        return self._call(h1.run, self.mk, self.arg_root, self.src, gate=gate, **kw)

    def run_to(self, k):
        for i in range(1, k + 1):
            assert self.run(self.D[i]) == 0, f"{self.D[i]} 처리 실패"
        return self

    def corp(self, code, **kw):
        kw.setdefault("source", "https://example.com/공시")
        kw.setdefault("source_data", self.src)                   # 기록 시각(at)도 가짜 시계로(같은 실행 = 같은 지문)
        kw.setdefault("gate", False)                             # 시험은 관문 끔(관문 시험은 따로)
        if kw.get("delist") or kw.get("cancel_delist"):
            kw.setdefault("confirm", code)                       # 단계 4 F-3: 같은 코드를 한 번 더(확인 시험은 따로)
        return self._call(h1.corp_action, self.mk, code, root=self.arg_root, **kw)

    @property
    def mdir(self):
        return self.root / self.mk

    def states(self):
        return h1.load_market(self.mk, self.root, repair=False).states

    def head(self):
        return json.loads((self.mdir / "HEAD.json").read_text(encoding="utf-8"))

    def meta(self):
        return json.loads((self.mdir / "meta.json").read_text(encoding="utf-8"))

    def last(self):
        return self.head()["last_date"]

    def ledger_shas(self):
        return {rel: fs.file_sha(self.mdir / rel) for rel in h1.LEDGER_RELS}

    def snap(self):
        """멱등 대상 파일(장부 6개·meta·HEAD·backup·판정 기록)의 sha256."""
        out = {k: v for k, v in fs.tree_sha(self.mdir).items()
               if k not in ("calendar.jsonl", "corp_actions.jsonl")}
        dl = h1.decisions_path(self.root, self.mk)
        out["analyst_cache.jsonl"] = fs.file_sha(dl) if dl.exists() else None
        return out

    def runs(self):
        return fs.read_lines(self.root / "runs.jsonl")

    def ends(self):
        return [r for r in self.runs() if r.get("event") == "end"]

    def errors(self):
        return fs.read_lines(self.root / "errors.jsonl")

    def fp(self):
        return h1.ledger_fingerprint(self.states())

    def recheck(self, allowed=None):
        """저장된 파일만으로 장부 전체를 다시 점검(보고서·재현과 같은 길)."""
        st = self.states()
        cal = h1._last_ok_calendar_line(self.root, self.mk)["dates"]
        dec = h1.DecisionLog(h1.decisions_path(self.root, self.mk), read_only=True)
        probs = []
        for arm in h1.ARMS:
            probs += h1_check.check_ledger(self.mk, arm, st[arm], cal, dec, allowed)
        probs += h1_check.check_pair(self.mk, st["A0"], st["A1"], dec)
        return probs


def us_h(tmp_path, upto=None, **kw):
    h = H(tmp_path, us_world(), hs.S_A, hs.plan_a, hs.FakeAsk(hs.ASK_A), **kw)
    if upto is not None:
        assert h.start() == 0
        h.run_to(upto)
    return h


def kr_h(tmp_path, upto=None, world=None, S="2026-02-02", plan=plan_kr, **kw):
    h = H(tmp_path, world or kr_world(), S, plan, hs.FakeAsk(), **kw)
    if upto is not None:
        assert h.start() == 0
        h.run_to(upto)
    return h


def fmt_l(probs):
    return "\n".join(f"{p.code} {p.arm}/{p.trainer} {p.date}: {p.detail}" for p in h1_check.errors(probs))


def allowed_now():
    return {(h1.code_hash()[0], h1.env_key(h1.env_info()))}


def no_l_logs(h):
    assert not (h.root / "errors.jsonl").exists(), h.errors()
    assert not (h.root / "restarts.jsonl").exists()


# ============================ T-F1 ============================

def test_T_F1a_경로_모양과_밖_경로_거절(tmp_path):
    root = tmp_path / "h1"
    for mk in ("us", "kr"):
        ps = [h1.ledger_path(mk, a, t, root) for a in h1.ARMS for t in h1.TRAINERS]
        assert len(set(ps)) == 6
        for p in ps:
            rel = p.relative_to(root).parts
            assert rel[0] == mk and rel[1] in h1.ARMS and rel[2].startswith("team_") and rel[2].endswith(".json")
    assert h1.ledger_path("us", "A0", "마라토너", root) == root / "us" / "A0" / "team_마라토너.json"
    assert {r for r in h1.LEDGER_RELS} == {f"{a}/team_{t}.json" for a in h1.ARMS for t in h1.TRAINERS}
    for bad in (("us", "A2", "마라토너"), ("us", "A0", "../마라토너"), ("us", "A0", "모름")):
        with pytest.raises(ValueError):
            h1.ledger_path(*bad, root)
    for parts in (("..", "x.json"), ("us", "..", "..", "x"), ("a/b",), ("",)):
        with pytest.raises(ValueError):
            h1.h1_path(root, *parts)
    root.mkdir()
    (tmp_path / "밖").mkdir()
    (root / "us").symlink_to(tmp_path / "밖")                 # 심볼릭 링크로 밖으로 새는 길
    with pytest.raises(ValueError):
        h1.ledger_path("us", "A0", "마라토너", root)
    # 기본 위치는 state/h1 아래, 운영 상태 폴더 자체·그 위 폴더는 H1 폴더로 받지 않는다
    assert h1.H1_DIR == team.STATE_DIR / "h1"
    assert h1.ledger_path("kr", "A1", "스프린터") == team.STATE_DIR / "h1" / "kr" / "A1" / "team_스프린터.json"
    for bad_root in (team.STATE_DIR, team.STATE_DIR.parent):
        with pytest.raises(ValueError):
            h1.ledger_path("kr", "A0", "마라토너", bad_root)
    for mk in ("us", "kr"):                                   # 운영 장부 경로와 겹치지 않음
        ops = {team._path(t, mk) for t in h1.TRAINERS}
        assert not ops & {h1.ledger_path(mk, a, t) for a in h1.ARMS for t in h1.TRAINERS}


def test_T_F1b_운영_장부_격리(tmp_path, monkeypatch):
    state = tmp_path / "state"
    (state / "kr").mkdir(parents=True)
    ops = [state / "team_마라토너.json", state / "team_스프린터.json", state / "kr" / "team_마라토너.json",
           state / "kr" / "team_파이오니어.json"]
    for i, p in enumerate(ops):
        p.write_text(json.dumps({"schema": "v1-usd-1", "가짜": i}), encoding="utf-8")
        os.utime(p, ns=(1_700_000_000_000_000_000 + i, 1_700_000_000_000_000_000 + i))
    before = {p: (fs.file_sha(p), p.stat().st_mtime_ns) for p in ops}
    monkeypatch.setattr(team, "STATE_DIR", state)
    monkeypatch.setattr(h1, "H1_DIR", state / "h1")

    def forbidden(*a, **k):
        raise AssertionError("H1 경로가 운영 장부 함수를 불렀어요")
    monkeypatch.setattr(team, "_load", forbidden)
    monkeypatch.setattr(team, "_save", forbidden)
    monkeypatch.setattr(main, "load_state_file", forbidden)
    kw = {"root": state / "h1", "default_root": True}
    for h in (us_h(tmp_path, **kw), kr_h(tmp_path, **kw)):
        assert h.start() == 0                                 # 기본 위치(H1_DIR = state/h1) 그대로
        for k in range(1, 4):
            assert h.run(h.D[k]) == 0
        assert h1.status(h.mk)
        assert h.corp("AAA" if h.mk == "us" else "005930", delist=True, last_date=h.D[3]) == 0
        assert h.run(h.D[4]) == 0
    after = {p: (fs.file_sha(p), p.stat().st_mtime_ns) for p in ops}
    assert after == before
    made = {p.relative_to(state).parts[0] for p in state.rglob("*") if p.is_file() and p not in ops}
    assert made == {"h1"}                                     # H1 은 state/h1 아래에만 썼다


# ============================ T-F4 · T-FETCH ============================

def _raw_frame(dates, kr=False, zero=(), nan_close=(), vol_name="Volume"):
    n = len(dates)
    o = np.linspace(100, 120, n)
    df = pd.DataFrame({"Open": o, "High": o * 1.01, "Low": o * 0.99, "Close": o + 0.5,
                       vol_name: np.full(n, 1e6)}, index=pd.DatetimeIndex(dates))
    for d in zero:
        df.loc[pd.Timestamp(d), ["Open", "High", "Low"]] = 0.0
        df.loc[pd.Timestamp(d), vol_name] = 0.0
    for d in nan_close:
        df.loc[pd.Timestamp(d), "Close"] = float("nan")
    return df


def test_T_F4_대기_자산_경로(monkeypatch):
    assert h1.idle_code("us") == markets.MARKETS["us"].benchmark == "SPY"
    assert h1.idle_code("kr") == markets.MARKETS["kr"].benchmark == "KS200"
    calls = []
    df = _raw_frame(pd.bdate_range("2026-10-01", "2026-11-04"))

    def fake_load_prices(code, start, now=None, market="us", allow_index=False):
        calls.append((code, start, market, allow_index, now))
        return df
    monkeypatch.setattr(main, "load_prices", fake_load_prices)
    now = datetime(2026, 11, 4, 23, 5, tzinfo=KST)
    assert h1.load_idle("kr", now) is df and calls[-1] == ("KS200", team.START, "kr", True, now)
    assert h1.load_idle("us", now) is df and calls[-1] == ("SPY", team.START, "us", False, now)
    assert h1.live_source("kr").benchmark(now) is df and calls[-1][3] is True

    def fail(*a, **k):
        raise ValueError("받기 실패")
    monkeypatch.setattr(main, "load_prices", fail)
    assert h1.load_idle("kr", now) is None and h1.load_idle("us", now) is None


def test_T_F4_국내_KS200_은_allow_index_문과_22시30분(monkeypatch):
    dates = pd.bdate_range("2026-10-01", "2026-11-04")
    fake = types.SimpleNamespace(DataReader=lambda code, start: _raw_frame(dates))
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fake)
    early = h1.load_idle("kr", datetime(2026, 11, 4, 22, 29, tzinfo=KST))
    late = h1.load_idle("kr", datetime(2026, 11, 4, 22, 31, tzinfo=KST))
    assert early.index[-1].date().isoformat() == "2026-11-03"     # 22:30 전에는 오늘 봉 버림
    assert late.index[-1].date().isoformat() == "2026-11-04"
    with pytest.raises(ValueError):                              # 종목 받기 문으로는 KS200 이 안 들어온다
        main.load_prices("KS200", team.START, market="kr")


def test_T_F4_하루_기록의_지수_시가_종가는_그_시세(tmp_path):
    h = us_h(tmp_path, upto=3)
    for st in (h.states()[a][t] for a in h1.ARMS for t in h1.TRAINERS):
        for row in st["days"]:
            ts = pd.Timestamp(row["date"])
            assert row["idle_open"] == float(h.w.idle.loc[ts, "Open"])
            assert row["idle_close"] == float(h.w.idle.loc[ts, "Close"])


@pytest.mark.parametrize("vol_name", ["Volume", "거래량"])
def test_T_FETCH_main_load_prices_와_같은_단계(monkeypatch, vol_name):
    dates = pd.bdate_range("2026-09-01", "2026-11-04")
    zero = [dates[10].date().isoformat(), dates[11].date().isoformat()]
    raw = _raw_frame(dates, zero=zero, nan_close=[dates[20].date().isoformat()], vol_name=vol_name)
    seen = []
    fake = types.SimpleNamespace(DataReader=lambda code, start: (seen.append((code, start)), raw.copy())[1])
    monkeypatch.setitem(sys.modules, "FinanceDataReader", fake)
    for now in (datetime(2026, 11, 4, 15, 59, tzinfo=KST), datetime(2026, 11, 4, 16, 1, tzinfo=KST)):
        got = h1.fetch("kr", "005930", now)
        want = main.load_prices("005930", team.START, now=now, market="kr")
        pd.testing.assert_frame_equal(got.df, want)
        assert got.halt_dates == frozenset(zero)
        assert not set(zero) & {d.date().isoformat() for d in got.df.index}
    assert seen[0] == ("005930", team.START)
    now = datetime(2026, 11, 4, 16, 20, tzinfo=ET)
    got = h1.fetch("us", "AAPL", now)
    pd.testing.assert_frame_equal(got.df, main.load_prices("AAPL", team.START, now=now))
    assert got.halt_dates == frozenset()                          # 미국은 정지 날짜 없음
    with pytest.raises(ValueError):
        h1.fetch("kr", "AAPL", now)                              # 국내 시장에 미국 종목 금지

    def broken(code, start):
        raise ConnectionError("끊김")
    monkeypatch.setitem(sys.modules, "FinanceDataReader", types.SimpleNamespace(DataReader=broken))
    assert h1.fetch("us", "AAPL", now) is None
    monkeypatch.setitem(sys.modules, "FinanceDataReader",
                        types.SimpleNamespace(DataReader=lambda c, s: raw.iloc[:0]))
    assert h1.fetch("us", "AAPL", now) is None


# ============================ T-D (D1~D7) ============================

def _d_case(h, kind):
    """kind 상황을 만들고, 되돌리는 함수를 돌려준다. 보유: 마라토너 AAA·BBB·CCC(D1~), 스프린터 BBB·CCC…"""
    t = h.D[5]
    src = h.src
    if kind == "D1":
        src.idle_missing = True
        return lambda: setattr(src, "idle_missing", False)
    if kind == "D2":
        src.missing = {"BBB"}
        return lambda: setattr(src, "missing", set())
    if kind == "D3":
        src.drop = {"BBB": {t}}
        return lambda: setattr(src, "drop", {})
    if kind == "D4":
        src.idle_drop = {h.D[2]}                       # 이미 처리한 날짜가 사라짐
        return lambda: setattr(src, "idle_drop", set())
    if kind == "D5":
        src.idle_drop = {t}                            # 새로 처리할 구간에 구멍 (D6 시각에 실행)
        return lambda: setattr(src, "idle_drop", set())
    if kind == "D6":
        bump = h.D[3]

        def f(df, now):
            df.loc[pd.Timestamp(bump), "Close"] = df.loc[pd.Timestamp(bump), "Close"] * 1.01
            return df
        src.transform["BBB"] = f
        return lambda: src.transform.pop("BBB")
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["D1", "D2", "D3", "D4", "D5", "D6"])
def test_T_D_자료_문제는_4_그_봉_저장_안함_다음_실행_정상(tmp_path, kind):
    h = us_h(tmp_path, upto=4)
    snap = h.snap()
    undo = _d_case(h, kind)
    t_run = h.D[6] if kind == "D5" else h.D[5]
    assert h.run(t_run) == 4
    assert h.snap() == snap and h.last() == h.D[4]               # 그 봉(과 그 뒤) 저장 안 함
    end = h.ends()[-1]
    assert end["exit_code"] == 4 and [p["code"] for p in end["problems"] if p["level"] == "D"] == [kind]
    no_l_logs(h)
    undo()
    assert h.run(t_run) == 0
    assert h.last() == t_run
    no_l_logs(h)


def test_T_D_D6_분할_의심_비율_알림(tmp_path):
    h = us_h(tmp_path, upto=4)
    h.src.transform["BBB"] = fs.split_after("2026-01-01", 2, ET)  # 모든 지난 값이 ÷2
    assert h.run(h.D[5]) == 4
    msg = [p for p in h.ends()[-1]["problems"] if p["code"] == "D6"][0]["detail"]
    assert "분할 의심(비율 r=2)" in msg and "BBB" in msg


def test_T_D_D7_기준_지수_늦음은_7_앞_봉까지_저장(tmp_path):
    h = us_h(tmp_path, upto=3)
    h.src.idle_until = h.D[4]                                     # SPY 는 D4 까지, AAPL·MSFT 는 D5 확정 봉이 있음
    assert h.run(h.D[5]) == 7
    assert h.last() == h.D[4]                                     # 처리할 수 있던 D4 는 저장
    end = h.ends()[-1]
    assert end["exit_code"] == 7 and end["bars"] == [h.D[4]]
    assert [p["code"] for p in end["problems"] if p["level"] == "D"] == ["D7"]
    no_l_logs(h)
    assert h.run(h.D[5]) == 7 and h.last() == h.D[4]              # 처리할 봉 없음 + D7 → 7
    h.src.idle_until = None
    assert h.run(h.D[5]) == 0 and h.last() == h.D[5]
    no_l_logs(h)


def test_T_D_확인용_대형주를_못_받으면_W5(tmp_path):
    h = us_h(tmp_path, upto=1)
    h.src.missing = {"AAPL", "MSFT"}
    h.src.idle_until = h.D[2]
    assert h.run(h.D[3]) == 0                                     # D7 판단 불가 → 경고만
    codes = [p["code"] for p in h.ends()[-1]["problems"]]
    assert codes.count("W5") == 2 and "D7" not in codes


# ============================ T-LATEDATA (실행 수준) ============================

def test_T_LATEDATA_보유_종목_행이_늦게_오면_D3_다음_실행_정상(tmp_path):
    h = kr_h(tmp_path, upto=3)
    t = h.D[4]
    held = sorted(h.states()["A0"]["마라토너"]["positions"])
    assert held
    h.src.drop = {held[0]: {t}}                                   # 원본에도 그 날 행이 없음(정지 아님)
    snap = h.snap()
    assert h.run(t) == 4 and h.snap() == snap
    assert [p["code"] for p in h.ends()[-1]["problems"] if p["level"] == "D"] == ["D3"]
    h.src.drop = {}
    assert h.run(t) == 0 and h.last() == t                        # 다음 실행이 정상 처리(L4·L15 없음)
    assert h1_check.errors(h.recheck(allowed_now())) == []
    no_l_logs(h)


def test_T_LATEDATA_T_RETRO_국내_Volume0_행은_정지로_진행_정지일_marks_는_D6_안남(tmp_path):
    base = kr_world()
    D = [base.at("2026-02-02", k) for k in range(8)]
    w = kr_world(halts={"000660": [D[3], D[4]]})                  # 마라토너가 D1 부터 보유
    h = kr_h(tmp_path, world=w, upto=5)
    st = h.states()["A0"]["마라토너"]
    days = {r["date"]: r for r in st["days"]}
    assert "000660" in days[D[3]]["halted"] and "000660" in days[D[4]]["halted"]
    assert days[D[3]]["marks"]["000660"] == w.close("000660", D[2])  # 정지 전 마지막 종가로 평가(D6 도 안 남)
    assert h1_check.errors(h.recheck(allowed_now())) == []


# ============================ T-RETRO ============================

def test_T_RETRO_분할_의심_corp_action_split_다음_실행_정상(tmp_path):
    h = us_h(tmp_path, upto=4)
    t = h.D[5]
    h.src.transform["BBB"] = fs.split_after(t, 2, ET)             # t 부터 1주 → 2주, 제공처가 지난 값을 ÷2
    before = h.states()
    holders = [(a, tn) for a in h1.ARMS for tn in h1.TRAINERS if "BBB" in before[a][tn]["positions"]]
    assert holders
    snap = h.snap()
    assert h.run(t) == 4 and h.snap() == snap
    assert "분할 의심(비율 r=2)" in [p for p in h.ends()[-1]["problems"] if p["code"] == "D6"][0]["detail"]
    assert h.corp("BBB", split=2, date=t) == 0
    after = h.states()
    for a, tn in holders:
        b, n = before[a][tn], after[a][tn]
        assert n["positions"]["BBB"]["shares"] == 2 * b["positions"]["BBB"]["shares"]
        assert n["positions"]["BBB"]["buy_price"] == b["positions"]["BBB"]["buy_price"] / 2
        assert n["wallet"].holdings["BBB"].shares == 2 * b["wallet"].holdings["BBB"].shares
        mark = b["days"][-1]["marks"]["BBB"]                      # 평가액은 그 순간 그대로
        assert n["wallet"].holdings["BBB"].shares * (mark / 2) == b["wallet"].holdings["BBB"].shares * mark
        assert n["days"] == b["days"] and n["fills"] == b["fills"]
        assert n["corp_actions"][-1]["kind"] == "split" and n["corp_actions"][-1]["applied_after"] == h.D[4]
    assert h.head()["last_date"] == h.D[4]
    ca = fs.read_lines(h.mdir / "corp_actions.jsonl")
    ch = fs.read_lines(h.root / "changes.jsonl")
    assert ca[-1]["kind"] == "split" and ch[-1]["kind"] == "corp-action:split"
    assert h.run(t) == 0 and h.run(h.D[6]) == 0
    assert h.last() == h.D[6]
    assert h1_check.errors(h.recheck(allowed_now())) == []
    no_l_logs(h)


def test_T_RETRO_정수가_아니면_split_거절(tmp_path):
    h = us_h(tmp_path, upto=2)
    snap = h.snap()
    assert h.corp("BBB", split=1.0001, date=h.D[3]) == 9         # 주식 수 × r 이 정수가 아님 → ⑦-3
    assert h.snap() == snap
    assert h.corp("SPY", split=2, date=h.D[3]) == 9               # 지수에는 분할 없음
    assert h.corp("BBB", split=2, delist=True, date=h.D[3]) == 9  # 하나만


# ============================ T-DELIST ============================

def test_T_DELIST_시세를_못_받는_상태에서_등록_다음_run_진행(tmp_path):
    h = us_h(tmp_path, upto=4)
    t = h.D[5]
    st0 = h.states()
    holders = [(a, tn) for a in h1.ARMS for tn in h1.TRAINERS if "CCC" in st0[a][tn]["positions"]]
    assert holders
    h.src.missing = {"CCC"}
    assert h.run(t) == 4                                          # D2
    assert h.corp("CCC", delist=True, last_date=t) == 9           # last_date > 장부 last_date → 거절
    P = 12.3456
    assert h.corp("CCC", delist=True, last_date=h.D[4], last_close=P) == 0
    assert h.corp("CCC", delist=True, last_date=h.D[4], last_close=P) == 9   # 두 번 등록 거절
    assert h.run(t) == 0 and h.last() == t
    st = h.states()
    m = markets.MARKETS["us"]
    for a, tn in holders:
        f = [x for x in st[a][tn]["fills"] if x["purpose"] == "delist"]
        assert len(f) == 1 and f[0]["date"] == t and f[0]["price"] == P and f[0]["order_id"] is None
        q = st0[a][tn]["positions"]["CCC"]["shares"]
        E = P * (1 - m.slippage)
        assert f[0]["qty"] == q and f[0]["cash_delta"] == E * q - E * q * m.fee_rate   # 미국 매도세 0
        assert "CCC" not in st[a][tn]["positions"] and "CCC" not in st[a][tn]["wallet"].holdings
    for a in h1.ARMS:
        for tn in h1.TRAINERS:
            assert not [o for o in st[a][tn]["pending"] if o["code"] == "CCC"]
            assert st[a][tn]["corp_actions"][-1]["kind"] == "delist"
    assert h1_check.errors(h.recheck(allowed_now())) == []
    assert h.run(h.D[6]) == 0                                     # 그 뒤로도 CCC 시세 없이 진행(W4 만)
    assert "W4" in [p["code"] for p in h.ends()[-1]["problems"]]
    # 가격을 바꾼 정리 체결 → L23
    bad = json.loads(json.dumps({a: {tn: h1.ledger_to_json(s, "us") for tn, s in by.items()} for a, by in st.items()}))
    a, tn = holders[0]
    next(x for x in bad[a][tn]["fills"] if x["purpose"] == "delist")["price"] = P * 1.1
    probs = h1_check.check_ledger("us", a, bad[a], None, None)
    assert "L23" in {p.code for p in h1_check.errors(probs)}
    no_l_logs(h)


def test_T_DELIST_last_close_를_비우면_마지막_marks(tmp_path):
    h = us_h(tmp_path, upto=3)
    marks = [r["marks"]["CCC"] for r in h.states()["A0"]["스프린터"]["days"] if "CCC" in r["marks"]]
    assert h.corp("CCC", delist=True, last_date=h.D[3]) == 0
    reg = h.states()["A1"]["마라토너"]["corp_actions"][-1]
    assert reg["last_close"] == marks[-1] and reg["last_close_from"] == f"marks {h.D[3]}"


# ============================ T-CORR ============================

def test_T_CORR_정정_확정(tmp_path):
    h = us_h(tmp_path, upto=4)
    bump = h.D[3]
    old_close = float(h.w.raw["BBB"].loc[pd.Timestamp(bump), "Close"])

    def f(df, now):
        df.loc[pd.Timestamp(bump), "Close"] = old_close * 1.003
        return df
    h.src.transform["BBB"] = f
    assert h.run(h.D[5]) == 4
    msg = [p for p in h.ends()[-1]["problems"] if p["code"] == "D6"][0]["detail"]
    assert "분할 의심" not in msg
    before = h.states()
    h.src.at(h.D[5])
    assert h.corp("BBB", accept_correction=True, source_data=h.src) == 0
    after = h.states()
    for a in h1.ARMS:
        for tn in h1.TRAINERS:
            b, n = before[a][tn], after[a][tn]
            for k in ("positions", "fills", "days", "pending", "orders", "skips"):
                assert n[k] == b[k]                                # 장부(체결·평가·보유)는 그대로
            ca = n["corp_actions"][-1]
            assert ca["kind"] == "correction" and ca["code"] == "BBB"
            assert {"date": bump, "field": "close", "old": old_close, "new": old_close * 1.003} in ca["items"]
    assert h.run(h.D[5]) == 0 and h.last() == h.D[5]
    assert h.corp("BBB", accept_correction=True, source_data=h.src) == 9   # 이제 차이가 없음
    no_l_logs(h)


# ============================ T-AMEND ============================

def test_T_AMEND_세율_줄_추가(tmp_path, monkeypatch):
    base = tuple(h1.KR_SELL_TAX)
    h = kr_h(tmp_path, upto=2)
    snap = h.snap()
    added = base + (("2027-01-01", 0.0015),)
    monkeypatch.setattr(h1, "KR_SELL_TAX", added)
    assert h.run(h.D[3]) == 3 and h.snap() == snap               # 규칙 다름 → 아무것도 저장 안 함
    assert "stock_sell_tax" in h.ends()[-1]["message"]
    assert h1.amend_rules("kr", "", h.root, gate=False) == 9      # 출처 없음
    assert h1.amend_rules("kr", "https://law.go.kr/세율", h.root, gate=False) == 0
    assert h.meta()["rules"]["stock_sell_tax"][-1] == ["2027-01-01", 0.0015]
    assert h.ledger_shas() == {k: v for k, v in snap.items() if k in h1.LEDGER_RELS}   # 장부 내용은 그대로
    assert h.head()["meta_sha256"] == fs.file_sha(h.mdir / "meta.json") and "-amend-rules-" in h.head()["run_id"]
    ch = fs.read_lines(h.root / "changes.jsonl")[-1]
    assert ch["kind"] == "amend-rules" and ch["added_rows"] == [["2027-01-01", 0.0015]]
    assert h1.amend_rules("kr", "https://law.go.kr/세율", h.root, gate=False) == 0   # 이미 같음
    assert h.run(h.D[3]) == 0 and h.last() == h.D[3]
    meta = h.meta()
    # 앞줄을 바꾼 표 → 거절
    changed = list(added)
    changed[-2] = ("2026-01-01", 0.0021)
    monkeypatch.setattr(h1, "KR_SELL_TAX", tuple(changed))
    assert h1.amend_rules("kr", "https://law.go.kr/세율", h.root, gate=False) == 3
    assert h.meta() == meta
    # 시행일이 이미 처리한 봉 이전인 줄 추가 → 거절(지난 체결을 바꾸게 됨)
    monkeypatch.setattr(h1, "KR_SELL_TAX", added + (("2026-02-03", 0.001),))
    assert h1.amend_rules("kr", "https://law.go.kr/세율", h.root, gate=False) == 3
    assert h.meta() == meta
    # 세율 말고 다른 규칙이 다르면 amend-rules 로 못 고침(재시작 대상)
    monkeypatch.setattr(h1, "KR_SELL_TAX", added)
    monkeypatch.setattr(h1, "RETRO_DAYS", 6)
    assert h1.amend_rules("kr", "https://law.go.kr/세율", h.root, gate=False) == 3
    assert h.run(h.D[4]) == 3 and h.meta() == meta


# ============================ T-CAL ============================

def test_T_CAL_국내_22시29분_22시31분(tmp_path):
    h = kr_h(tmp_path, upto=3)
    t = h.D[4]
    h.src.idle_until = h.D[3]                                     # KS200 에 t 봉이 아직 없음, 종목에는 있음
    assert h.run(t, hh=22, mm=29) == 0 and h.last() == h.D[3]     # 22:30 전 → D7 아님(이미 처리됨)
    assert h.run(t, hh=22, mm=31) == 7 and h.last() == h.D[3]     # 22:30 지남 → D7
    h.src.idle_until = None
    assert h.run(t, hh=22, mm=31) == 0 and h.last() == t
    no_l_logs(h)


def test_T_CAL_2026_에서_2027_첫_봉_연도_파일_늦음(tmp_path):
    # 실제 KRX 처럼 12-25·12-31·01-01 휴장(2b-2 검토 C-18): 2026 마지막 봉 12-30 → 2027 첫 봉 01-04
    w = fs.drop_days(kr_world(start="2026-06-01", end="2027-02-26"), ["2026-12-25", "2026-12-31", "2027-01-01"])
    S = "2026-12-24"
    h = kr_h(tmp_path, world=w, S=S, upto=2)                      # 12-28, 12-29 처리
    h.src.idle_until = "2026-12-30"                               # 2027.csv 가 아직 없음
    jan4 = "2027-01-04"
    assert h.run(clock=datetime(2027, 1, 4, 23, 5, tzinfo=KST)) == 7
    assert h.last() == "2026-12-30"                               # 처리할 수 있던 12-30 은 저장
    assert h.ends()[-1]["bars"] == ["2026-12-30"]
    h.src.idle_until = None
    assert h.run(clock=datetime(2027, 1, 4, 23, 10, tzinfo=KST)) == 0 and h.last() == jan4
    h.src.idle_from = "2027-01-01"                                # 2026.csv 를 한 번 못 받음 → 처리한 날짜가 사라짐
    snap = h.snap()
    assert h.run(clock=datetime(2027, 1, 5, 23, 5, tzinfo=KST)) == 4
    assert [p["code"] for p in h.ends()[-1]["problems"] if p["level"] == "D"] == ["D4"]
    assert h.snap() == snap
    h.src.idle_from = None
    assert h.run(clock=datetime(2027, 1, 5, 23, 5, tzinfo=KST)) == 0 and h.last() == "2027-01-05"
    cal = fs.read_lines(h.mdir / "calendar.jsonl")
    assert [c["check"] for c in cal][-4:] == ["D7", "ok", "D4", "ok"]
    last = cal[-1]
    assert last["dates"][0] == w.prev(S) and last["dates"][-1] == "2027-01-05" and last["processed"] == ["2027-01-05"]
    assert "2026-12-31" not in last["dates"] and "2027-01-01" not in last["dates"]
    assert last["sha256"] == h1._sha256_bytes(json.dumps(last["dates"], separators=(",", ":")).encode())
    no_l_logs(h)


def test_T_CAL_처리한_구간에_날짜가_끼어들면_D4(tmp_path):
    h = us_h(tmp_path)
    h.src.idle_drop = {h.D[2]}                                    # 처음에 SPY 에 D2 가 없던 제공처
    for c in US_CODES:
        h.src.drop[c] = {h.D[2]}
    assert h.start() == 0
    assert h.run(h.D[1]) == 0 and h.run(h.D[3]) == 0              # D1 → D3 (D2 는 아무도 없음)
    h.src.idle_drop = set()
    h.src.drop = {}                                               # 나중에 D2 가 생김
    assert h.run(h.D[4]) == 4
    assert "달력 바뀜" in [p for p in h.ends()[-1]["problems"] if p["code"] == "D4"][0]["detail"]


# ============================ T-CUT · T-DST · T-LATE · T-LLMTIME ============================

def plan_cut(D):
    return {"마라토너": {"buy": [("035420", D[4])]}}


def test_T_CUT_국내_20시와_22시31분(tmp_path):
    h = kr_h(tmp_path, plan=plan_cut, upto=3)
    t = h.D[4]
    assert h.run(t, hh=20, mm=0) == 0                             # 종목 오늘 봉 있음, KS200 오늘 봉 버림
    assert h.last() == h.D[3]
    st = h.states()
    assert not any(o["signal_date"] == t for a in h1.ARMS for tn in h1.TRAINERS for o in st[a][tn]["pending"])
    dec = h1.DecisionLog(h1.decisions_path(h.root, h.mk), read_only=True)
    assert not [r for r in dec.records() if r["date"] == t]
    assert "D7" not in [p["code"] for p in h.ends()[-1]["problems"]]
    assert h.run(t, hh=22, mm=31) == 0 and h.last() == t          # 22:31 → 오늘 처리
    st = h.states()
    assert [o["code"] for o in st["A0"]["마라토너"]["pending"] if o["signal_date"] == t] == ["035420"]


def test_T_DST_미국_서머타임_앞뒤_07시10분(tmp_path):
    w = us_world(start="2025-10-01", end="2026-11-30")
    assert h1.next_open("us", "2026-03-06") == datetime(2026, 3, 9, 9, 30, tzinfo=ET)
    assert h1.next_open("us", "2026-03-06").utcoffset().total_seconds() == -4 * 3600     # 서머타임(EDT)
    assert h1.next_open("us", "2026-10-30").utcoffset().total_seconds() == -5 * 3600     # 표준시(EST)
    for S, bars in (("2026-03-04", ["2026-03-05", "2026-03-06", "2026-03-09", "2026-03-10"]),
                    ("2026-10-28", ["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"])):
        h = H(tmp_path, w, S, None, hs.FakeAsk(), name=f"h1-{S}")
        assert h.start() == 0
        for t in bars:
            when = fs.run_at("us", t)
            assert when.hour == 7 and when.minute == 10 and when.tzinfo == KST
            assert h.run(clock=when) == 0
            assert h.last() == t                                  # 바로 전 미국 거래일이 확정 봉
            row = h.states()["A1"]["마라토너"]["days"][-1]
            assert row["mode"] == "llm" and row["late"] is False


def test_T_LATE_2봉_밀림은_차례로_late_6봉은_6(tmp_path):
    h = us_h(tmp_path, upto=3)
    n_calls = len(h.ask.calls)
    assert h.run(h.D[5]) == 0                                     # D4·D5 를 한 번에
    end = h.ends()[-1]
    assert end["bars"] == [h.D[4], h.D[5]] and end["late_bars"] == [h.D[4]]
    rows = {r["date"]: r for r in h.states()["A0"]["마라토너"]["days"]}
    assert rows[h.D[4]]["late"] is True and rows[h.D[4]]["mode"] == "late"
    assert rows[h.D[5]]["late"] is False and rows[h.D[5]]["mode"] == "llm"
    dec = h1.DecisionLog(h1.decisions_path(h.root, h.mk), read_only=True)
    late_recs = [r for r in dec.records() if r["date"] == h.D[4]]
    assert late_recs and {r["status"] for r in late_recs} == {"late_no_llm"}   # 늦은 봉은 LLM 을 안 부름(폴백)
    d5 = {r["code"] for r in dec.records() if r["date"] == h.D[5]}
    assert {c for _, codes in h.ask.calls[n_calls:] for c in codes} == d5      # 이번 실행의 LLM 호출은 D5 후보뿐
    assert h1_check.errors(h.recheck(allowed_now())) == []
    snap = h.snap()
    assert h.run(h.D[11]) == 6 and h.snap() == snap               # 6봉 밀림 → 창 실패, 저장 안 함
    assert h.ends()[-1]["exit_code"] == 6


def test_T_LLMTIME_국내_08시59분은_llm_10시는_late(tmp_path):
    for hh, mm, mode in ((8, 59, "llm"), (10, 0, "late")):
        h = kr_h(tmp_path, upto=2, name=f"h1-{hh}")
        t = h.D[3]
        n = len(h.ask.calls)
        nxt = pd.Timestamp(h.D[4])
        assert h.run(clock=datetime(nxt.year, nxt.month, nxt.day, hh, mm, tzinfo=KST)) == 0
        assert h.last() == t                                      # 10:00 에도 KS200 오늘 봉은 없음 → 어제 봉
        row = h.states()["A0"]["마라토너"]["days"][-1]
        assert row["date"] == t and row["mode"] == mode and row["late"] is (mode == "late")
        if mode == "late":
            assert len(h.ask.calls) == n                          # LLM 0번


# ============================ T-GATE ============================

def _pass(root, tag, env, **kw):
    """재현 통과 기록(단계 4 F-1 모양: files·data_golden_sha256). tag None = 지금 코드,
    글자 = h1_data.py 하나만 다른 가짜 코드(fs.code_variant — ⑥-i 로 허용되는 변경 모양)."""
    return fs.record_pass(root, fs.code_variant(tag), env, **kw)


def _restart(h, note="시험", reason="L", evidence=True):
    """restart(단계 4 F-4): --confirm 시장 + 사유 코드. evidence 면 그 사유 L 의 근거(이 창의 errors.jsonl L 한 줄)를 먼저 더한다."""
    if evidence and reason == "L":
        lm = h1._lenient_meta(h.mk, h.root)
        fs.give_l_evidence(h.root, h.mk, lm.get("start_date") or "unknown",
                           lm.get("created_at") or "2000-01-01T00:00:00+00:00")
    return h1.restart(h.mk, reason, h.root, confirm=h.mk, note=note)


def test_T_GATE_지문_env_다르면_3_파일_0개(tmp_path, monkeypatch):
    h = us_h(tmp_path)
    early = fs.run_at("us", hs.S_A, hh=6, mm=0)                   # 시작 전 거절은 성공한 start 보다 앞 시각
    assert h.start(gate=True, clock=early) == 3                   # replay_pass.json 없음
    assert sorted(p.name for p in h.root.iterdir()) == ["h1-us.lock", "runs.jsonl"]
    end = h.ends()[-1]
    assert end["exit_code"] == 3 and end["command"] == "start" and end["start_date"] == "unknown"
    ch, env = h1.code_hash()[0], h1.env_info()
    assert _pass(h.root, None, {**env, "pandas": "0.0.1"}) == 1   # 지문은 같고 env 가 다름
    assert h.start(gate=True, clock=early) == 3
    assert sorted(p.name for p in h.root.iterdir()) == ["changes.jsonl", "h1-global.lock", "h1-us.lock",
                                                         "replay_pass.json", "replay_pass.seal.json", "runs.jsonl"]
    _pass(h.root, "0", env)                                       # env 는 같고 지문이 다름
    assert h.start(gate=True, clock=early) == 3
    _pass(h.root, None, env)
    assert len(h1.replay_pass_entries(h.root)) == 3               # 추가만(지난 줄 그대로)
    assert h.start(gate=True) == 0 and h.run(h.D[1], gate=True) == 0
    snap = h.snap()
    F = fs.code_variant("f")
    monkeypatch.setattr(h1, "code_hash", lambda *a, **k: F)       # 코드가 바뀐 것처럼(재현 통과 기록 없음)
    assert h.run(h.D[2], gate=True) == 3 and h.snap() == snap
    end = h.ends()[-1]
    assert end["exit_code"] == 3 and end["start_date"] == hs.S_A   # 관문 거절도 창 S 로 기록(C-3)
    monkeypatch.undo()
    assert "관문 거절 1" in "\n".join(h1.status("us", h.root))


def test_C5_통과_기록이_줄거나_바뀌면_L_이_아니라_3(tmp_path, monkeypatch):
    h = us_h(tmp_path)
    ch, env = h1.code_hash()[0], h1.env_info()
    A = fs.code_variant("a")
    _pass(h.root, "a", env)                                       # 옛 코드 A(h1_data.py 만 다름)
    monkeypatch.setattr(h1, "code_hash", lambda *a, **k: A)
    assert h.start(gate=True) == 0 and h.run(h.D[1], gate=True) == 0
    monkeypatch.undo()
    _pass(h.root, None, env)                                      # ⑥-i 허용 변경: 새 코드 B 통과 기록을 더함
    assert h.run(h.D[2], gate=True) == 0
    rp = h.root / "replay_pass.json"
    whole = rp.read_bytes()
    entries = json.loads(whole)
    rp.write_text(json.dumps(entries[1:]), encoding="utf-8")      # 재현 도구가 옛 줄을 지우고 새로 씀
    snap = h.snap()
    assert h.run(h.D[3], gate=True) == 3 and h.snap() == snap     # L22(종료 코드 2) 가 아니라 관문 거절
    assert "줄었거나 바뀜" in h.ends()[-1]["message"] and not (h.root / "errors.jsonl").exists()
    entries[0]["env"] = {**env, "numpy": "9"}
    rp.write_text(json.dumps(entries), encoding="utf-8")          # 지난 줄 내용 바뀜
    assert h.run(h.D[3], gate=True) == 3
    rp.write_text(json.dumps(json.loads(whole) + [{"code_hash": "c" * 64, "env": env}]), encoding="utf-8")
    assert h.run(h.D[3], gate=True) == 3                          # 봉인 없이 손으로 더한 줄
    assert "봉인 없이" in h.ends()[-1]["message"]
    with pytest.raises(h1.H1Refused):
        _pass(h.root, "d", env)                                   # 망가진 상태에서는 기록도 거절(아무것도 안 씀)
    rp.write_bytes(whole)
    assert h.run(h.D[3], gate=True) == 0
    # 봉인을 쓴 뒤 목록을 쓰기 전에 꺼짐 → 목록이 한 줄 짧음은 받아 줌, 다음 기록이 봉인을 맞춤
    seal = h.root / "replay_pass.seal.json"
    with monkeypatch.context() as mp:
        _crash_on(mp, lambda dst, seen: dst.name == "replay_pass.json")
        with pytest.raises(Crash):
            _pass(h.root, "e", env)
    assert len(json.loads(seal.read_text())["digests"]) == 3 and len(json.loads(rp.read_text())) == 2
    assert h.run(h.D[4], gate=True) == 0
    assert _pass(h.root, "e", env) == 3
    # 지난 봉 지문이 통과 기록에 없으면(봉인째 지워짐) 3
    seal.unlink()
    rp.unlink()
    _pass(h.root, None, env)
    assert h.run(h.D[5], gate=True) == 3
    assert "replay_pass.json 에 없어요" in h.ends()[-1]["message"]
    assert not (h.root / "errors.jsonl").exists()


def test_T_GATE_규칙_상수가_다르면_3(tmp_path, monkeypatch):
    h = us_h(tmp_path, upto=1)
    snap = h.snap()
    monkeypatch.setattr(h1, "MAX_LATE_TOTAL", 11)
    assert h.run(h.D[2]) == 3 and h.snap() == snap
    assert "max_late_total" in h.ends()[-1]["message"]


# ============================ T-LOCK ============================

class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_T_LOCK_30분_넘게_잠금이면_5_모든_명령(tmp_path, monkeypatch):
    root = tmp_path / "h1"
    monkeypatch.setattr(h1, "H1_DIR", root)
    root.mkdir()
    clock = FakeClock()
    slept = []

    def fake_sleep(s):
        slept.append(s)
        clock.t += s
    monkeypatch.setattr(h1, "_lock_clock", clock)
    monkeypatch.setattr(h1, "_lock_sleep", fake_sleep)
    fd = os.open(root / "h1-us.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)                                # 다른 명령이 잠금을 쥔 상황(시장마다)
    fd2 = os.open(root / "h1-kr.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd2, fcntl.LOCK_EX)
    try:
        cmds = [["start", "--market", "us"], ["run", "--market", "kr"],
                ["restart", "--market", "us", "--confirm", "us", "--reason", "L"],
                ["corp-action", "--market", "us", "--code", "AAA", "--delist", "--last-date", "2026-01-02",
                 "--confirm", "AAA", "--source", "x"],
                ["amend-rules", "--market", "kr", "--source", "x"], ["status", "--market", "us"]]
        for argv in cmds:
            before = clock.t
            slept.clear()
            assert h1.cli(argv) == 5, argv
            assert clock.t - before >= h1.LOCK_WAIT_S and slept   # 기다렸다가(가짜 시계) 포기
        assert h1.run("us", root, fs.FakeSource(us_world())) == 5
        lines = fs.read_lines(root / "runs.jsonl")
        assert [r["command"] for r in lines] == ["start", "run", "restart", "corp-action", "amend-rules", "status",
                                                 "run"]
        assert {r["event"] for r in lines} == {"lock_timeout"}
    finally:
        os.close(fd)
        os.close(fd2)


def test_T_LOCK_기다리는_동안_풀리면_진행(tmp_path, monkeypatch):
    h = us_h(tmp_path)
    h.root.mkdir()
    fd = os.open(h.root / "h1-us.lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(fd, fcntl.LOCK_EX)
    clock = FakeClock()

    def release(s):
        clock.t += s
        fcntl.flock(fd, fcntl.LOCK_UN)
    monkeypatch.setattr(h1, "_lock_clock", clock)
    monkeypatch.setattr(h1, "_lock_sleep", release)
    try:
        assert h.start() == 0
    finally:
        os.close(fd)


# ============================ T-HEAD ============================

def _crash_on(monkeypatch, pred):
    real = os.replace
    seen = []

    def fake(src, dst, *a, **k):
        if pred(Path(dst), seen):
            raise Crash(str(dst))
        seen.append(Path(dst))
        return real(src, dst, *a, **k)
    monkeypatch.setattr(h1.os, "replace", fake)


def _is_ledger(p):
    return p.parent.name in h1.ARMS and p.name.startswith("team_") and p.suffix == ".json"


def test_T_HEAD_3개_바꾼_뒤_멈춤은_백업으로_되살려_같은_결과(tmp_path, monkeypatch):
    twin = us_h(tmp_path, upto=4, name="twin")                    # 끊기지 않은 실행
    h = us_h(tmp_path, upto=3)
    head0 = h.head()
    with monkeypatch.context() as mp:
        _crash_on(mp, lambda dst, seen: _is_ledger(dst) and sum(map(_is_ledger, seen)) == 3)
        with pytest.raises(Crash):
            h.run(h.D[4])
    assert h.head() == head0
    changed = [r for r in h1.LEDGER_RELS if fs.file_sha(h.mdir / r) != head0["files"][r]]
    assert len(changed) == 3                                      # 6개 중 3개만 바뀐 채 멈춤
    assert (h.mdir / "backup" / head0["run_id"]).is_dir()
    n = len(h.ask.calls)
    assert h.run(h.D[4]) == 0
    assert h.ends()[-1]["restored_from_backup"] == head0["run_id"]
    assert len(h.ask.calls) == n                                  # 판정 기록 재사용
    assert h.fp() == twin.fp()
    no_l_logs(h)


def test_T_HEAD_corp_action_뒤_같은_last_date_에서_멈춤(tmp_path, monkeypatch):
    h = us_h(tmp_path, upto=3)
    assert h.corp("CCC", delist=True, last_date=h.D[3]) == 0      # 같은 last_date 에서 장부를 바꾸는 명령
    head_ca = h.head()
    assert head_ca["last_date"] == h.D[3] and "-corp-action-" in head_ca["run_id"]
    with monkeypatch.context() as mp:
        _crash_on(mp, lambda dst, seen: _is_ledger(dst) and sum(map(_is_ledger, seen)) == 2)
        with pytest.raises(Crash):
            h.run(h.D[4])
    bdir = h.mdir / "backup" / head_ca["run_id"]
    assert bdir.is_dir()
    assert all(fs.file_sha(bdir / r) == head_ca["files"][r] for r in h1.LEDGER_RELS)   # 백업 = corp-action 뒤 상태
    assert h.run(h.D[4]) == 0 and h.last() == h.D[4]
    assert h.ends()[-1]["restored_from_backup"] == head_ca["run_id"]


def test_T_HEAD_HEAD_도_백업도_안_맞으면_L24(tmp_path):
    h = us_h(tmp_path, upto=2)
    p = h.mdir / "A1" / "team_스프린터.json"
    p.write_bytes(p.read_bytes().replace(b'"days"', b'"days" ', 1))   # 내용은 같아도 글자가 바뀜
    assert not (h.mdir / "backup" / h.head()["run_id"]).exists()
    assert h.run(h.D[3]) == 2
    err = h.errors()[-1]
    assert err["problems"][-1]["code"] == "L24" and h.mdir.is_dir()
    assert not (h.root / "restarts.jsonl").exists()


def test_T_HEAD_백업은_최근_10개(tmp_path, monkeypatch):
    monkeypatch.setattr(h1, "BACKUPS_KEEP", 3)
    h = us_h(tmp_path, upto=6)
    names = sorted(p.name for p in (h.mdir / "backup").iterdir())
    assert len(names) == 3
    assert h1.BACKUPS_KEEP == 3


# ============================ T-STRICT ============================

def _rewrite_ledger(h, rel, fn, fix_head=True):
    p = h.mdir / rel
    p.write_bytes(fn(p.read_bytes()))
    if fix_head:                                                  # HEAD 도 맞춰 고쳐 "읽기"까지 가게
        head = h.head()
        head["files"][rel] = fs.file_sha(p)
        (h.mdir / "HEAD.json").write_text(json.dumps(head, ensure_ascii=False, indent=1), encoding="utf-8")


@pytest.mark.parametrize("how", ["깨진JSON", "NaN", "형식", "칸빠짐", "HEAD깨짐"])
def test_T_STRICT_깨진_장부는_2_새로_시작_안함(tmp_path, how):
    h = us_h(tmp_path, upto=2)
    rel = "A0/team_마라토너.json"
    if how == "깨진JSON":
        _rewrite_ledger(h, rel, lambda b: b[:-20])
    elif how == "NaN":
        _rewrite_ledger(h, rel, lambda b: b.replace(b'"prev_value": ', b'"prev_value": NaN, "x": ', 1))
    elif how == "형식":
        _rewrite_ledger(h, rel, lambda b: b.replace(b'"h1-us-2"', b'"h1-us-1"', 1))
    elif how == "칸빠짐":
        def drop(b):
            d = json.loads(b)
            del d["positions"]
            return json.dumps(d, ensure_ascii=False).encode()
        _rewrite_ledger(h, rel, drop)
    else:
        (h.mdir / "HEAD.json").write_text('{"last_date": "2026-02-04"', encoding="utf-8")
    before = fs.tree_sha(h.mdir)
    assert h.run(h.D[3]) == 2
    assert h.errors()[-1]["problems"][-1]["code"] == "L24"
    assert fs.tree_sha(h.mdir) == before                          # 보관·새 지갑으로 덮기 없음
    assert h.start() == 8                                         # 새로 시작도 안 함(폴더가 있음)
    assert not (h.root / "archive").exists()


# ============================ T-NEWSTART ============================

def test_T_NEWSTART_명시_시작_규칙(tmp_path):
    h = us_h(tmp_path)
    assert h.start() == 0
    assert h.start() == 8                                         # 폴더 있음
    import shutil
    shutil.rmtree(h.mdir)                                         # 실수로 지움
    assert h.start() == 8                                         # 성공한 start 흔적 + 재시작 기록 없음
    assert h.run(h.D[1]) == 8                                     # run 은 장부 없으면 8
    h.mdir.mkdir()
    (h.mdir / "x").write_text("임시")
    path = _restart(h, "시험: 폴더 보관")
    assert path.parent.name == "archive" and path.name.startswith("us-") and not h.mdir.exists()
    rs = fs.read_lines(h.root / "restarts.jsonl")
    assert [r["status"] for r in rs] == ["moving", "done"] and rs[0]["reason"] == "L"
    assert rs[0]["note"] == "시험: 폴더 보관" and rs[0]["evidence"]
    assert rs[0]["restart_id"] == rs[1]["restart_id"] and rs[0]["archive"] == f"archive/{path.name}"
    assert h.start() == 0                                         # restart 뒤 start 는 됨
    assert h.meta()["restart_no"] == 1 and h.states()["A0"]["마라토너"]["h1"]["restart_no"] == 1
    assert h.ends()[-1]["exit_code"] == 0


def test_T_NEWSTART_starting_에_쓰다_멈추면_다음_start_가_지우고_다시(tmp_path, monkeypatch):
    h = us_h(tmp_path)
    h.src.idle_missing = True
    assert h.start() == 4                                         # D1 → 아무 폴더도 없음
    assert not h.mdir.exists() and not (h.root / "us.starting").exists()
    h.src.idle_missing = False
    with monkeypatch.context() as mp:
        _crash_on(mp, lambda dst, seen: dst.name == "us")
        with pytest.raises(Crash):
            h.start()
    assert (h.root / "us.starting").is_dir() and not h.mdir.exists()
    assert h.start() == 0
    assert h.mdir.is_dir() and not (h.root / "us.starting").exists()
    assert not (h.root / "restarts.jsonl").exists()               # 재시작으로 세지 않음
    assert any("지우고 처음부터" in n for n in h.ends()[-1]["notes"])
    assert h.run(h.D[1]) == 0


def test_T_NEWSTART_재시작_상한(tmp_path):
    h = us_h(tmp_path)
    for i in range(h1.MAX_RESTARTS):
        assert h.start() == 0
        _restart(h, f"시험 {i}")
    assert h.start() == 0
    with pytest.raises(h1.H1Refused) as e:
        _restart(h, "세 번째")
    assert e.value.code == 8 and h.mdir.is_dir()
    with pytest.raises(h1.H1Refused) as e:
        h1.restart("us", "  ", h.root, confirm="us")              # 사유 코드가 아님
    assert e.value.code == 9
    with pytest.raises(h1.H1Refused) as e:
        h1.restart("us", "L", h.root)                             # --confirm 없음
    assert e.value.code == 9


# ============================ T-UNIV ============================

def test_T_UNIV_미국_종목군은_첫_S_목록_순서로_고정(tmp_path):
    order = ["MSFT", "JJJ", "AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "AAPL"]
    h = us_h(tmp_path, universe=order)
    assert h.start() == 0
    u = json.loads((h.root / "universe" / "us.json").read_text(encoding="utf-8"))
    assert u["codes"] == order and u["market"] == "us" and u["fetched_at"] == fs.run_at("us", hs.S_A).isoformat()
    assert u["fdr_version"] == h1.env_info()["FinanceDataReader"] and u["source"] == "screener.universe(40)"
    assert h.src.universe_calls == 1
    sha = fs.file_sha(h.root / "universe" / "us.json")
    assert h.meta()["universe_sha256"] == sha
    h.src.uni = ["AAA", "BBB"]                                     # 다음날 S&P 목록이 바뀜
    assert h.run(h.D[1]) == 0 and h.src.universe_calls == 1
    _restart(h)
    assert h.start() == 0 and h.src.universe_calls == 1           # 재시작해도 첫 목록
    assert h.meta()["universe_sha256"] == sha
    p = h.root / "universe" / "us.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["codes"] = list(reversed(d["codes"]))                       # 파일을 고치면 L22
    p.write_text(json.dumps(d), encoding="utf-8")
    assert h.run(h.D[1]) == 2
    assert h.errors()[-1]["problems"][-1]["code"] == "L22"


def test_T_UNIV_운영_자료의_종목군(monkeypatch):
    assert h1.live_source("kr").universe() == list(markets.KR_UNIVERSE.values())
    seen = []
    monkeypatch.setattr(screener, "universe", lambda n, market="us": (seen.append(n), ["A", "B"])[1])
    assert h1.live_source("us").universe() == ["A", "B"] and seen == [h1.N_UNIVERSE] == [40]


# ============================ T-F6 ============================

def test_T_F6a_주문_실행기_경로는_H1_밖():
    for mk in ("us", "kr"):
        for tn in h1.TRAINERS:
            p = order_runner.state_path(mk, tn)
            assert "h1" not in p.relative_to(order_runner.STATE_DIR).parts


def test_T_F6b_H1_장부만_있으면_주문_0건(tmp_path, monkeypatch):
    h = us_h(tmp_path, root=tmp_path / "state" / "h1")
    assert h.start() == 0
    st = h.states()
    assert any(st[a][tn]["pending"] for a in h1.ARMS for tn in h1.TRAINERS)   # 대기 주문이 있는 H1 장부
    monkeypatch.setattr(order_runner, "STATE_DIR", tmp_path / "state")
    assert order_runner.load_states("us", log=lambda *a: None) == {}
    broker = FakeBroker()
    now = datetime(2026, 2, 3, 10, 0, tzinfo=ET)
    assert order_runner.place("us", broker, now=now, close_fn=lambda *a: 1.0, log=lambda *a: None) == []
    assert broker.placed == []


def test_T_F6c_소스_격리():
    assert "h1" not in (ROOT / "order_runner.py").read_text(encoding="utf-8")
    for f in sorted(ROOT.glob("h1*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        assert not names & {"order_runner", "broker"}, f.name


# ============================ T-F7 ============================

def test_T_F7_같은_봉_두번째_run_은_아무것도_안_바뀜(tmp_path):
    h = us_h(tmp_path, upto=4)
    snap = h.snap()
    n_calls, n_runs = len(h.ask.calls), len(h.runs())
    n_cal = len(fs.read_lines(h.mdir / "calendar.jsonl"))
    assert h.run(h.D[4], hh=8, mm=0) == 0                         # 같은 확정 봉으로 다시
    assert h.snap() == snap
    assert len(h.ask.calls) == n_calls                            # 팀장 0번
    assert len(h.runs()) == n_runs + 2                            # 실행 일지는 줄이 더해짐
    assert len(fs.read_lines(h.mdir / "calendar.jsonl")) == n_cal + 1
    assert h.ends()[-1]["bars"] == []


def test_T_F7_봉마다_scan_frames_한_번_두_장부_같은_후보(tmp_path, monkeypatch):
    h = us_h(tmp_path, upto=2)
    calls = []
    real = screener.scan_frames

    def counting(*a, **k):
        calls.append(k.get("asof"))
        return real(*a, **k)
    monkeypatch.setattr(screener, "scan_frames", counting)
    assert h.run(h.D[4]) == 0                                     # D3·D4 두 봉
    assert calls == [h.D[3], h.D[4]]
    st = h.states()
    for tn in h1.TRAINERS:
        assert [r["screened"] for r in st["A0"][tn]["days"]] == [r["screened"] for r in st["A1"][tn]["days"]]


def test_claude_cli_version_은_실행마다_한_번_llm_일_때만(tmp_path, monkeypatch):
    h = us_h(tmp_path, upto=2)
    n = []

    def counted():
        n.append(1)
        return CLI_VER
    real_call = h._call

    def call(fn, *a, **k):                                        # 도우미의 바꿔 끼우기 위에 세는 함수를 얹음
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(team, "BRAINS", h.brains)
            mp.setattr(screener, "BRAINS", h.brains)
            mp.setattr(analyst, "analyze_logged", h.ask)
            mp.setattr(analyst, "claude_cli_version", counted)
            return fn(*a, **k)
    h._call = call
    assert h.run(h.D[4]) == 0 and len(n) == 1                     # 두 봉을 처리해도 한 번
    assert h.run(h.D[4]) == 0 and len(n) == 1                     # 처리할 봉이 없으면 부르지 않음
    assert h._call(h1.run, "us", h.root, h.at(h.D[5]).src, leader_mode="replay", gate=False) == 0
    assert len(n) == 1                                            # 재현 방식은 부르지 않음
    rec = [r for r in h1.DecisionLog(h1.decisions_path(h.root, h.mk), read_only=True).records() if r["date"] == h.D[4]]
    assert rec and {r["cli_version"] for r in rec} == {CLI_VER}
    h._call = real_call
    with pytest.raises(ValueError):
        h1.run("us", h.root, h.src, leader_mode="late")
    modes = h.ends()[-1]["bar_modes"]                             # 잘못된 방식은 잠금 전에 거절(일지 없음)
    assert set(modes) == {h.D[5]} and modes[h.D[5]]["mode"] == "replay"


# ============================ T-JSONL ============================

def test_T_JSONL_HEAD_전에_꺼지면_남은_판정_줄을_재사용(tmp_path, monkeypatch):
    twin = us_h(tmp_path, upto=2, name="twin")
    h = us_h(tmp_path, upto=1)
    dl = h1.decisions_path(h.root, h.mk)
    with monkeypatch.context() as mp:
        _crash_on(mp, lambda dst, seen: dst.name == "HEAD.json")
        with pytest.raises(Crash):
            h.run(h.D[2])
    lines = dl.read_bytes().count(b"\n")
    assert lines > h.head()["decision_log"]["lines"]              # 장부보다 먼저 쓴 판정 줄이 남음
    n = len(h.ask.calls)
    assert h.run(h.D[2]) == 0
    assert len(h.ask.calls) == n                                  # LLM 0번
    assert dl.read_bytes().count(b"\n") == lines
    assert h.fp() == twin.fp()


def test_T_JSONL_반쯤_쓴_마지막_줄은_run_이_잘라_내고_기록(tmp_path):
    h = us_h(tmp_path, upto=1)
    dl = h1.decisions_path(h.root, h.mk)
    whole = dl.read_bytes()
    dl.write_bytes(whole + b'{"key": "us|2026-02-03|')
    assert h.run(h.D[2]) == 0
    assert dl.read_bytes().startswith(whole)
    assert h.ends()[-1]["decision_log_truncated"]["bytes"] == len(b'{"key": "us|2026-02-03|')


def test_T_JSONL_지난_줄이_바뀌면_L18(tmp_path):
    h = us_h(tmp_path, upto=2)
    dl = h1.decisions_path(h.root, h.mk)
    b = dl.read_bytes()
    dl.write_bytes(b.replace(b'"verdict":"buy"', b'"verdict":"veto"', 1))
    assert h.run(h.D[3]) == 2
    assert {p["code"] for p in h.errors()[-1]["problems"]} == {"L18"}


# ============================ L 오류 → errors.jsonl (지문 참고용) ============================

def test_L_오류는_errors_jsonl_에_지문과_함께_2(tmp_path, monkeypatch):
    h = us_h(tmp_path, upto=1)
    snap = h.snap()
    real = h1_check.check_day

    def with_l(market, date, *a, **k):                            # 점검이 L 을 찾은 상황
        return real(market, date, *a, **k) + [h1_check.Problem("L", "L5", market, "A1", "마라토너", date, "시험용 L")]
    monkeypatch.setattr(h1_check, "check_day", with_l)
    assert h.run(h.D[2]) == 2                                     # 그 봉은 저장 안 함(판정 기록 줄은 먼저 쓰여도 됨)
    assert {k: v for k, v in h.snap().items() if k != "analyst_cache.jsonl"} == \
        {k: v for k, v in snap.items() if k != "analyst_cache.jsonl"}
    err = h.errors()[-1]
    assert err["date"] == h.D[2] and [p["code"] for p in err["problems"] if p["level"] == "L"] == ["L5"]
    assert err["run_id"] == h.ends()[-1]["run_id"] and err["start_date"] == hs.S_A
    assert isinstance(err["fingerprint"], str) and len(err["fingerprint"]) == 64
    assert err["fingerprint"] != h.fp()                           # 저장하려던(처리 뒤) 장부의 지문
    monkeypatch.setattr(h1_check, "check_day", real)
    assert h.run(h.D[2]) == 0
    assert h.fp() == err["fingerprint"]                           # 같은 봉을 다시 처리하면 같은 지문(④-나 재료)


def test_끝까지_못_간_L_예외도_errors_jsonl_에_번호와_지문(tmp_path, monkeypatch):
    h = us_h(tmp_path, upto=1)
    real = team.run_trainer

    def broken(tname, *a, **k):
        if tname == "스프린터":
            raise h1.H1LogicError("시험용: 엄격 시세 묶음에 없는 종목", code="L6")
        return real(tname, *a, **k)
    monkeypatch.setattr(team, "run_trainer", broken)
    assert h.run(h.D[2]) == 2 and h.last() == h.D[1]
    err = h.errors()[-1]
    assert err["exception"]["code"] == "L6" and err["date"] == h.D[2]
    assert isinstance(err["fingerprint"], str) and len(err["fingerprint"]) == 64   # 그때까지 장부 6개의 지문


def test_사전_조건_어긋남은_4(tmp_path, monkeypatch):
    h = us_h(tmp_path, upto=1)
    snap = h.snap()
    monkeypatch.setattr(h1, "_halted_on", lambda fetched, codes, t: frozenset({"BBB"}))   # 거래했는데 '정지'라고 함
    assert h.run(h.D[2]) == 4 and h.snap() == snap
    assert [p["code"] for p in h.ends()[-1]["problems"] if p["level"] == "D"] == ["PRE"]
    no_l_logs(h)


def test_status_는_파일을_고치지_않음(tmp_path):
    h = us_h(tmp_path, upto=2)
    p = h.mdir / "A0" / "team_마라토너.json"
    p.write_bytes(p.read_bytes() + b" ")                          # HEAD 와 다름
    before = fs.tree_sha(h.mdir)
    lines = h1.status("us", h.root)
    assert "장부를 읽지 못함" in lines[0] and fs.tree_sha(h.mdir) == before


def test_예상_밖_예외는_2_지문_없음(tmp_path, monkeypatch):
    h = us_h(tmp_path, upto=1)

    def bug(*a, **k):
        raise KeyError("버그")
    monkeypatch.setattr(h1, "run_bar", bug)
    assert h.run(h.D[2]) == 2
    err = h.errors()[-1]
    assert err["fingerprint"] is None and "KeyError" in err["traceback"]


# ============================ status · 요약 · cli ============================

def test_status_와_요약(tmp_path):
    h = us_h(tmp_path, upto=3)
    lines = h1.status("us", h.root)
    text = "\n".join(lines)
    assert f"시작 S {hs.S_A}" in text and "판정 창 4/63" in text and "재시작 0/2" in text
    assert "A1 쉬는 돈=SPY" in text and "단위" in text
    assert "※ 3개월은 판단하기에 너무 짧다" in text
    units = sum(h.states()["A1"][tn]["wallet"].holdings["SPY"].shares for tn in h1.TRAINERS)
    assert f"SPY {units:.6f}단위" in text
    assert h1.status("kr", h.root)[0].startswith("[H1 kr 상태] 장부 없음")
    s = h1.summary_lines("us", h.states(), errors=0, data_stops=1)
    assert s[0] == f"[H1 us] 기준 봉 {h.D[3]} · 시작 {hs.S_A} · 판정 창 4/63"
    assert s[1].startswith("  A0 쉬는 돈=현금  $100,000 → $") and "자료 멈춤 1" in s[4]


def test_cli_인자_오류는_9(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(h1, "H1_DIR", tmp_path / "h1")
    assert h1.cli(["run"]) == 9                                   # --market 없음
    assert h1.cli(["run", "--market", "jp"]) == 9
    assert h1.cli(["fly", "--market", "us"]) == 9
    assert h1.cli(["status", "--market", "us"]) == 8              # 장부 없음
    assert "장부 없음" in capsys.readouterr().out
    assert h1.cli(["restart", "--market", "us", "--reason", "x"]) == 9          # --confirm 없음·사유 코드 아님
    assert h1.cli(["restart", "--market", "us", "--confirm", "us", "--reason", "x"]) == 9
    assert h1.cli(["restart", "--market", "us", "--confirm", "kr", "--reason", "L"]) == 9   # 다른 시장을 확인
    assert h1.cli(["restart", "--market", "us", "--confirm", "us", "--reason", "L"]) == 8   # 장부 없음


def test_cli_python_h1_py_로_돌면_같은_모듈(tmp_path):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, str(ROOT / "h1.py"), "run"], capture_output=True, text=True, cwd=str(tmp_path),
                       env=env, timeout=120)
    assert r.returncode == 9 and "명령 인자 오류" in r.stdout
    src = (ROOT / "h1.py").read_text(encoding="utf-8")
    assert src.rstrip().endswith("sys.exit(_h1.cli())")


# ============================ 여러 날 끝까지 (미국·국내) ============================

def plan_e2e_us(D):
    p = hs.plan_a(D)
    p["마라토너"]["buy"] += [("EEE", D[9]), ("III", D[13])]
    p["마라토너"]["sell"] += [("BBB", D[12])]
    p["스프린터"]["buy"] += [("FFF", D[8]), ("HHH", D[11])]
    p["스프린터"]["sell"] += [("DDD", D[10])]
    p["파이오니어"]["sell"] = [("GGG", D[10])]
    p["파이오니어"]["buy"] += [("JJJ", D[12])]
    return p


def plan_e2e_kr(D):
    return {"마라토너": {"buy": [("005930", D[0]), ("000660", D[0]), ("035420", D[3])], "sell": [("005930", D[11])]},
            "스프린터": {"buy": [("005380", D[2]), ("035420", D[1]), ("068270", D[7])], "sell": [("035420", D[13])]},
            "파이오니어": {"buy": [("105560", D[2])], "sell": [("105560", D[9])]}}


def _e2e_us(tmp_path, name):
    h = H(tmp_path, us_world(), hs.S_A, plan_e2e_us, hs.FakeAsk(hs.ASK_A), name=name)
    D = h.D
    assert h.start() == 0
    for k in range(1, 6):
        assert h.run(D[k]) == 0
    h.src.transform["BBB"] = fs.split_after(D[6], 2, ET)          # BBB 2:1 분할(D6)
    assert h.run(D[6]) == 4
    assert h.corp("BBB", split=2, date=D[6]) == 0
    assert h.run(D[6]) == 0 and h.run(D[7]) == 0 and h.run(D[8]) == 0
    h.src.missing = {"CCC"}                                       # CCC 상장폐지(D9 부터 시세 없음)
    assert h.run(D[9]) == 4
    assert h.corp("CCC", delist=True, last_date=D[8]) == 0
    assert h.run(D[9]) == 0 and h.run(D[10]) == 0
    assert h.run(D[12]) == 0                                      # 맥이 하루 꺼짐 → D11(늦은 봉)·D12
    assert h.ends()[-1]["late_bars"] == [D[11]]
    h.src.drop = {"BBB": {D[13]}}                                 # 매도 대기 중인 보유 종목의 늦은 자료 → D3
    assert h.run(D[13]) == 4
    h.src.drop = {}
    for k in range(13, 18):
        assert h.run(D[k]) == 0
    assert h.last() == D[17]
    return h


def _e2e_kr(tmp_path, name):
    base = kr_world()
    D = [base.at("2026-02-02", k) for k in range(20)]
    w = kr_world(halts={"005380": D[3:6], "000660": D[8:10]})     # 대기 매수 정지 가로지름 · 보유 정지
    h = H(tmp_path, w, "2026-02-02", plan_e2e_kr, hs.FakeAsk({"068270": ("Hold", 0.6)}),
          name=name)
    D = h.D
    assert h.start() == 0
    for k in range(1, 10):
        assert h.run(D[k]) == 0
    h.src.transform["035420"] = fs.split_after(D[10], 5, KST)     # 5:1 분할
    assert h.run(D[10]) == 4
    assert h.corp("035420", split=5, date=D[10]) == 0
    assert h.run(D[10]) == 0 and h.run(D[11]) == 0
    assert h.run(D[13]) == 0                                      # D12 늦은 봉
    h.src.drop = {"000660": {D[14]}}                              # 마라토너 보유 종목의 늦은 자료 → D3
    assert h.run(D[14]) == 4
    h.src.drop = {}
    for k in range(14, 18):
        assert h.run(D[k]) == 0
    assert h.last() == D[17]
    return h


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    out = {}
    with pytest.MonkeyPatch.context() as mp:
        def boom(*a, **k):
            raise AssertionError("시험이 진짜 claude 를 부르려 했어요")
        mp.setattr(analyst, "analyze_logged", boom)
        mp.setattr(analyst, "claude_cli_version", boom)
        mp.setattr(h1, "_lock_sleep", boom)
        for mk, fn in (("us", _e2e_us), ("kr", _e2e_kr)):
            out[mk] = [fn(tmp_path_factory.mktemp(f"e2e-{mk}-{i}"), "h1") for i in (1, 2)]
    return out


@pytest.mark.parametrize("mk", ["us", "kr"])
def test_E2E_여러_날_저장_파일만으로_다시_점검_L0(e2e, mk):
    h = e2e[mk][0]
    probs = h.recheck(allowed_now())
    assert h1_check.errors(probs) == [], fmt_l(probs)
    st = h.states()
    days = st["A0"]["마라토너"]["days"]
    assert len(days) == 18 and days[0]["date"] == h.S
    assert any(r["late"] for r in days)
    corp = st["A1"]["스프린터"]["corp_actions"]
    assert "split" in {c["kind"] for c in corp}
    if mk == "us":
        assert "delist" in {c["kind"] for c in corp}
        assert any(f["purpose"] == "delist" for a in h1.ARMS for tn in h1.TRAINERS for f in st[a][tn]["fills"])
    else:
        assert any(r["halted"] for r in days)
    assert not (h.root / "errors.jsonl").exists() and not (h.root / "restarts.jsonl").exists()
    for a in h1.ARMS:                                             # 체결이 실제로 많이 일어남
        assert sum(len(st[a][tn]["fills"]) for tn in h1.TRAINERS) >= 6


@pytest.mark.parametrize("mk", ["us", "kr"])
def test_E2E_두_번_돌린_실행의_장부_내용_지문이_같음(e2e, mk):
    a, b = e2e[mk]
    assert a.fp() == b.fp()
    assert a.ledger_shas() != {} and a.head()["last_date"] == b.head()["last_date"]
