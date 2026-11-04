"""H1 단계 2b-1 — 엔진 시험 (설계 docs/h1-forward-design.md §6, 이번 범위). 인터넷·claude·키 없음.

확인하는 것 (설계 시험 ID)
- T-START  S 는 입금만, S+1 A1 은 첫 전부 지수 → fund 지수 매도 → 매수 (손계산과 비트까지 같음), A0 는 평소대로
- T-A1-2   같은 시가 매도 1·매수 2: 매도 대금 먼저, 모자란 만큼만 지수 매도, 남은 돈 ≥ 1 이면 지수로 (두 경우)
- T-A1-3   현금+지수로도 모자람 → '현금 부족' 보류, 그 매수용 지수 매도 0, 단위 그대로
- T-A1-4   경계 여유(need ≈ avail·(1−1e-9) 위·아래), 지수 판 뒤 매수 실패를 억지로 만들면 H1LogicError(L11, 종료 코드 2)
- T-A1-5   쓸어 담기 문턱 0.99 / 1.00, 줄임 1e-12 실패 → 1e-9 성공, 셋 다 실패 → 오류
- T-A1-6   비용·세율: 미국·국내 지수 다리 수수료+슬리피지, 국내 지수 매도세 0, 국내 주식 매도세 = 날짜별 표(경계일 전날·당일)
- T-A1-7   (저장·읽기) 지수 단위 float.hex 그대로, 정수 주식은 int, 화면 6자리, 엄격 읽기
- T-A1-8   A0 는 지수 체결·보유 0
- T-SIG    신호 t → 체결 t+1 시가 (두 장부)
- T-F2     새 장부 총액·몫, 시작 예산 기준 상한, MAX_POSITIONS(대기 매수 포함), 확신도 0.5 경계·None·문자열, hold·veto
- T-F5a·b·c·d  같은 판정·없을 때만 호출·폴백 종류(missing_in_reply 포함)·글자 정리
- T-JSONL  (DecisionLog) 추가 전용·줄마다 fsync·반쯤 쓴 마지막 줄 잘라냄·중복 열쇠·중간 줄 깨짐·커밋 전 꺼짐 뒤 재사용
- T-LLMTIME (Leader) 국내 08:59/10:00 KST, 미국 09:29/09:31 ET, 묻기 직전 시각 재확인 → late_no_llm·late_calls
- T-SHADOW 그림자 서킷: 경계 위/아래, prev = 전날 하루 기록, S 는 prev 없음, events·first, 장부 안 바뀜
- T-ORDERS 주문 기록 상태(filled·skipped·dropped·pending), 사유 전체
- T-HALT   국내 3일 정지: 대기 매수 정지 뒤 첫 봉 체결(A1 은 그날만 지수 매도), 보유 종목 판단 쉼·보유일수·마지막 종가 평가,
           정지 종목 후보 제외
- T-DELIST (엔진 부분) 상장폐지 정리 a′
- T-FP     장부 내용 지문
- T-ENTRY  team.py 에 --h1 없음, team.run·run_trainer(h1=None) 경로에서 h1 이 sys.modules 에 없음(새 프로세스)
- T-LOOK   봉 t 를 전체 시세로 처리 == t 에서 자른 시세로, t 뒤 봉·t 종가를 흔들어도 t 시가 체결·전날까지 기록 그대로
- R2 식 대조: sim_team.py 의 시가 메서드를 글자 그대로 옮긴 계산과 h1 결과가 비트까지 같음
진짜 claude 는 절대 부르지 않는다: analyst.analyze_logged·analyze·claude_cli_version 을 부르면 실패하게 바꿔 끼운다.
"""
import json
import os
import subprocess
import sys
import textwrap
import typing
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyst      # noqa: E402
import h1           # noqa: E402
import h1_check     # noqa: E402
import h1_synth as hs  # noqa: E402
import main         # noqa: E402
import team         # noqa: E402
from paper_wallet import Holding, PaperWallet, shares_within_cap   # noqa: E402
from risk_guard import CircuitBreaker   # noqa: E402

ET, KST = ZoneInfo("America/New_York"), ZoneInfo("Asia/Seoul")
US = main.mkt("us")
FEE, SLIP = US.fee_rate, US.slippage


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    """진짜 claude 를 부르는 길을 모두 막는다(이 컨테이너에는 진짜 claude 가 있음)."""
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


@pytest.fixture(scope="module")
def sc_a(tmp_path_factory):
    """시나리오 A (h1_synth 설명) — D0~D7 처리. 여러 시험이 읽기만 한다."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(analyst, "analyze_logged", lambda *a, **k: (_ for _ in ()).throw(AssertionError("claude")))
        return hs.scenario_a(tmp_path_factory.mktemp("sc_a") / "analyst_cache.jsonl", upto=7)


def fills_on(st, t, **match):
    return [f for f in st["fills"] if f["date"] == t and all(f[k] == v for k, v in match.items())]


def hx(x):
    return float(x).hex()


# ======================= T-START =======================

def test_T_START_S_는_입금만_S1_은_첫_전부_지수_손계산(sc_a):
    S, D1 = sc_a.D[0], sc_a.D[1]
    w = sc_a.world
    s0 = sc_a.runner.results[0].states
    for arm in h1.ARMS:
        for t in h1.TRAINERS:
            st = s0[arm][t]
            assert st["fills"] == [] and st["wallet"].holdings == {}
            assert st["wallet"].cash == st["start_cash"] == h1.TOTALS["us"] * main.CONFIG["배분비율"][t]
            assert st["days"][0]["date"] == S and st["days"][0]["idle_units"] == 0
    # S+1 A1 마라토너 손계산 (R2 _sweep_to_index·_fill_buy·_raise_cash 의 식과 계산 순서)
    st = sc_a.runner.results[1].states["A1"]["마라토너"]
    Q = w.idle_bar(D1).open
    cash = 60000.0
    unit = Q * (1 + SLIP) * (1 + FEE)
    u0 = cash / unit * (1 - 1e-12)
    E0 = Q * (1 + SLIP)
    cash = cash - (E0 * u0 + E0 * u0 * FEE)
    units = u0
    exp = [("idle", "buy", "SPY", hx(u0), hx(cash))]
    u_net = Q * (1 - SLIP) - Q * (1 - SLIP) * FEE
    for code in ("AAA", "BBB"):
        P = w.open(code, D1)
        n = shares_within_cap(60000.0, 0.30, P, FEE, SLIP)
        E = P * (1 + SLIP)
        need = E * n + E * n * FEE
        short = need - cash
        assert short > 0
        u = min(units, short / u_net * (1 + 1e-9))
        pr = Q * (1 - SLIP) * u
        cash = cash + (pr - pr * FEE - pr * 0.0)
        units = units - u
        exp.append(("idle", "sell", "SPY", hx(u), hx(cash)))
        cash = cash - (E * n + E * n * FEE)
        exp.append(("stock", "buy", code, hx(n), hx(cash)))
    assert cash < 1                                        # 남은 돈 < 1 → 쓸어 담기 없음
    got = [(f["kind"], f["side"], f["code"], hx(f["qty"]), hx(f["cash_after"])) for f in fills_on(st, D1)]
    assert got == exp
    assert fills_on(st, D1)[0]["purpose"] == "start"
    assert [f["purpose"] for f in fills_on(st, D1)[1:]] == ["fund:AAA", "order", "fund:BBB", "order"]
    assert hx(st["wallet"].holdings["SPY"].shares) == hx(units) and hx(st["wallet"].cash) == hx(cash)
    # A0 는 현금으로 바로 산다
    a0 = sc_a.runner.results[1].states["A0"]["마라토너"]
    c0 = 60000.0
    for code in ("AAA", "BBB"):
        P = w.open(code, D1)
        n = shares_within_cap(60000.0, 0.30, P, FEE, SLIP)
        E = P * (1 + SLIP)
        c0 = c0 - (E * n + E * n * FEE)
    assert hx(a0["wallet"].cash) == hx(c0) and "SPY" not in a0["wallet"].holdings
    # 첫 매수 수량·체결가 = 시작 예산 기준 상한 · 그날 시가
    for f in fills_on(a0, D1):
        assert f["qty"] == shares_within_cap(60000.0, 0.30, f["price"], FEE, SLIP) and f["price"] == w.open(f["code"], D1)


# ======================= T-A1-2 =======================

def test_T_A1_2_매도1_매수2_매도대금_먼저_모자란_만큼만_지수(sc_a):
    D3 = sc_a.D[3]
    w = sc_a.world
    before = sc_a.runner.results[2].states["A1"]["스프린터"]
    after = sc_a.runner.results[3].states["A1"]["스프린터"]
    Q = w.idle_bar(D3).open
    cash = before["wallet"].cash
    units = before["wallet"].holdings["SPY"].shares
    sh = before["positions"]["AAA"]["shares"]
    P = w.open("AAA", D3)
    pr = P * (1 - SLIP) * sh
    cash = cash + (pr - pr * FEE - pr * 0.0)
    exp = [("stock", "sell", "AAA", hx(cash))]
    u_net = Q * (1 - SLIP) - Q * (1 - SLIP) * FEE
    for code in ("DDD", "EEE"):
        P = w.open(code, D3)
        n = shares_within_cap(30000.0, 0.20, P, FEE, SLIP)
        E = P * (1 + SLIP)
        need = E * n + E * n * FEE
        if need > cash:
            u = min(units, (need - cash) / u_net * (1 + 1e-9))
            p2 = Q * (1 - SLIP) * u
            cash = cash + (p2 - p2 * FEE - p2 * 0.0)
            units -= u
            exp.append(("idle", "sell", "SPY", hx(cash)))
        cash = cash - (E * n + E * n * FEE)
        exp.append(("stock", "buy", code, hx(cash)))
    got = [(f["kind"], f["side"], f["code"], hx(f["cash_after"])) for f in fills_on(after, D3)]
    assert got == exp
    # 이 날은 DDD 는 매도 대금으로, EEE 는 모자란 만큼만 지수를 팔아 산다(두 가지를 다 지남)
    assert [f["purpose"] for f in fills_on(after, D3)] == ["order", "order", "fund:EEE", "order"]
    assert after["wallet"].cash < 1 and hx(after["wallet"].holdings["SPY"].shares) == hx(units)


def test_T_A1_2_매도_대금이_남으면_쓸어_담기(tmp_path):
    """AAA 가 크게 올라 매도 대금이 두 매수보다 많은 날: 지수 매도 없이 사고, 남은 돈(≥1)은 지수로."""
    w = hs.world_a(crash={"AAA": ("2026-02-04", 2.5)})        # D2 종가부터 AAA 2.5배
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=3, world=w)
    D3 = sc.D[3]
    st = sc.runner.results[3].states["A1"]["스프린터"]
    before = sc.runner.results[2].states["A1"]["스프린터"]
    f = fills_on(st, D3)
    assert [(x["kind"], x["side"], x["code"], x["purpose"]) for x in f] == [
        ("stock", "sell", "AAA", "order"), ("stock", "buy", "DDD", "order"), ("stock", "buy", "EEE", "order"),
        ("idle", "buy", "SPY", "sweep")]
    Q = w.idle_bar(D3).open
    left = f[2]["cash_after"]
    assert left >= 1
    unit = Q * (1 + SLIP) * (1 + FEE)
    u = left / unit * (1 - 1e-12)
    assert hx(f[3]["qty"]) == hx(u)
    assert hx(st["wallet"].holdings["SPY"].shares) == hx(before["wallet"].holdings["SPY"].shares + u)
    assert st["wallet"].cash < 1


# ======================= 손으로 만든 장부 (fill 단위 시험) =======================

T1, T2 = "2026-02-03", "2026-02-04"


def hand_state(arm="A1", trainer="스프린터", *, cash, units=0.0, positions=None, pending=(), market="us",
               last=T1):
    st = h1.new_ledger(market, arm, trainer, "2026-02-02")
    w = st["wallet"]
    w.cash = cash
    if units:
        w.holdings[h1.idle_code(market)] = Holding(shares=units, avg_price=500.0)
    for code, (n, px) in (positions or {}).items():
        w.holdings[code] = Holding(shares=n, avg_price=px)
        st["positions"][code] = {"buy_price": px, "days_held": 1, "shares": n, "buy_date": T1}
    for code, action in pending:
        o = {"code": code, "action": action, "signal_date": T1, "reason": f"손 {action}", "note": None}
        st["pending"].append(o)
        st["orders"].append({"id": h1.order_id(o), "signal_date": T1, "code": code, "action": action,
                             "reason": o["reason"], "origin": "candidate" if action == "매수" else "sell_signal",
                             "created_on": T1, "status": "pending", "done_date": None, "why": None})
    st["last_date"] = last
    return st


def one_row(t, px):
    return pd.DataFrame({"Open": [px], "High": [px], "Low": [px], "Close": [px], "Volume": [1e6]},
                        index=pd.DatetimeIndex([t]))


def do_fill(st, *, t=T2, prices=None, idle=(500.0, 501.0), arm="A1", trainer="스프린터", market="us",
            halted=(), delist=None, cap=None):
    m = main.mkt(market)
    bar = h1.IdleBar(h1.idle_code(market), t, *idle)
    day = h1.H1Day(market, arm, bar, lambda tr, c: {}, start_date="2026-02-02", prev_cal_date=T1,
                   halted=frozenset(halted), delist=delist)
    cache = h1.StrictFrames({c: one_row(t, p) for c, p in (prices or {}).items()})
    logs = []
    day.fill(st, trainer, main.CONFIG["종목상한"][trainer] if cap is None else cap, t, cache, m, logs)
    return day, logs


def need_of(px, n, fee=FEE, slip=SLIP):
    E = px * (1 + slip)
    return E * n + E * n * fee


def u_net_of(Q, fee=FEE, slip=SLIP):
    return Q * (1 - slip) - Q * (1 - slip) * fee


# ======================= T-A1-3 =======================

def test_T_A1_3_현금_지수로도_모자라면_지수를_팔지_않고_보류():
    P = 100.0
    n = shares_within_cap(30000.0, 0.20, P, FEE, SLIP)
    need = need_of(P, n)
    units = (need - 0.5) * 0.5 / u_net_of(500.0)              # 현금 0.5 + 지수 ≈ need 의 절반
    st = hand_state(cash=0.5, units=units, pending=[("XYZ", "매수")])
    do_fill(st, prices={"XYZ": P})
    assert [f for f in st["fills"] if f["kind"] == "idle" and f["side"] == "sell"] == []
    assert st["wallet"].holdings["SPY"].shares == units and "XYZ" not in st["positions"]
    sk = st["skips"][-1]
    assert sk["kind"] == "현금부족" and sk["need"] == need and sk["avail"] == 0.5 + units * u_net_of(500.0)
    assert st["orders"][0]["status"] == "skipped" and st["orders"][0]["why"] == "현금부족"
    assert st["wallet"].log[-1]["종류"] == "보류"


def test_T_A1_3_시나리오_마라토너_네번째_매수는_두_장부_모두_보류(sc_a):
    D3 = sc_a.D[3]
    for arm in h1.ARMS:
        st = sc_a.states[arm]["마라토너"]
        assert [(s["code"], s["kind"]) for s in st["skips"] if s["date"] == D3] == [("DDD", "현금부족")]
        assert not any(f["purpose"] == "fund:DDD" for f in st["fills"])


# ======================= T-A1-4 =======================

@pytest.mark.parametrize("rel", [1e-7, 1e-11])
def test_T_A1_4_경계_여유_위아래(rel):
    P = 100.0
    n = shares_within_cap(30000.0, 0.20, P, FEE, SLIP)
    need = need_of(P, n)
    un = u_net_of(500.0)
    # 아래(살 수 있음): avail·(1−1e-9) 가 need 보다 조금 큼
    u_ok = need / (un * (1 - 1e-9)) * (1 + rel)
    st = hand_state(cash=0.0, units=u_ok, pending=[("XYZ", "매수")])
    do_fill(st, prices={"XYZ": P})
    assert "XYZ" in st["positions"]
    leg = [f for f in st["fills"] if f["purpose"] == "fund:XYZ"][0]
    assert leg["short"] == need and leg["qty"] == min(u_ok, need / un * (1 + 1e-9))
    # 위(보류): 조금 모자람 → 지수를 팔지 않는다
    u_no = need / (un * (1 - 1e-9)) * (1 - rel)
    st = hand_state(cash=0.0, units=u_no, pending=[("XYZ", "매수")])
    do_fill(st, prices={"XYZ": P})
    assert "XYZ" not in st["positions"] and st["skips"][-1]["kind"] == "현금부족"
    assert st["fills"] == [] and st["wallet"].holdings["SPY"].shares == u_no


def test_T_A1_4_지수_판_뒤_매수_실패는_L11(monkeypatch):
    """억지로 지수를 모자라게 팔면 매수가 실패 → 예외로 멈추지 않고 L11 을 적는다(2b-1 검토 B-3)."""
    monkeypatch.setattr(h1, "SHORT_MARGIN", -1e-6)           # 일부러 모자라게 팔게 만든다
    st = hand_state(cash=0.0, units=1000.0, pending=[("XYZ", "매수")])
    day, _ = do_fill(st, prices={"XYZ": 100.0})
    assert [p.code for p in day.problems] == ["L11"] and day.problems[0].level == "L"
    assert "XYZ" not in st["positions"] and st["orders"][0]["status"] == "skipped"


def test_T_A1_4_지수_판_뒤_매수_실패면_run_bar_는_저장_금지_결과와_지문(monkeypatch, tmp_path):
    """봉 전체로: L11 이 있으면 ok=False 지만 처리 뒤 장부와 내용 지문은 있다(errors.jsonl 의 '저장하려던 지문')."""
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=0)
    monkeypatch.setattr(h1, "SHORT_MARGIN", -1e-6)
    res = sc.bar(sc.D[1])
    assert not res.ok and {p.code for p in res.errors} >= {"L11"}
    assert isinstance(res.fingerprint, str) and len(res.fingerprint) == 64
    assert res.fingerprint == h1.ledger_fingerprint(res.states)
    assert all(p.arm == "A1" for p in res.errors if p.code == "L11")


# ======================= T-A1-5 =======================

@pytest.mark.parametrize("cash,swept", [(0.99, False), (1.0, True), (0.9999999999, False)])
def test_T_A1_5_쓸어담기_문턱(cash, swept):
    st = hand_state(cash=cash, units=10.0)
    do_fill(st)
    legs = [f for f in st["fills"] if f["purpose"] == "sweep"]
    assert bool(legs) == swept
    if swept:
        unit = 500.0 * (1 + SLIP) * (1 + FEE)
        assert hx(legs[0]["qty"]) == hx(cash / unit * (1 - 1e-12))
    else:
        assert st["wallet"].cash == cash


class FlakyWallet(PaperWallet):
    """지수 매수에서 처음 몇 번(실패 횟수)은 일부러 실패하는 지갑(줄임 다음 단계로 가는 길 시험용)."""
    fails = 1
    tried: list

    def buy(self, code, price, shares, date=None):
        self.tried.append(shares)
        if code == "SPY" and len(self.tried) <= self.fails:
            return False
        return super().buy(code, price, shares, date)


def _flaky_state(fails):
    st = hand_state(cash=5000.0, units=0.0)
    w = st["wallet"]
    fw = FlakyWallet(name=w.name, cash=w.cash, currency=w.currency, fee_rate=w.fee_rate,
                     sell_tax_rate=w.sell_tax_rate, slippage=w.slippage)
    fw.fails, fw.tried = fails, []
    st["wallet"] = fw
    return st, fw


def test_T_A1_5_줄임_1e12_실패면_1e9():
    st, fw = _flaky_state(1)
    do_fill(st)
    unit = 500.0 * (1 + SLIP) * (1 + FEE)
    assert [hx(x) for x in fw.tried] == [hx(5000.0 / unit * (1 - s)) for s in (1e-12, 1e-9)]
    assert hx(st["fills"][-1]["qty"]) == hx(5000.0 / unit * (1 - 1e-9))


def test_T_A1_5_줄임_셋_다_실패면_L11():
    st, fw = _flaky_state(3)
    day, _ = do_fill(st)
    assert len(fw.tried) == 3 and [p.code for p in day.problems] == ["L11"]
    assert st["wallet"].cash == 5000.0 and st["fills"] == []


# ======================= T-A1-6 =======================

def test_T_A1_6_국내_매도세_표_경계():
    assert h1.KR_SELL_TAX == (("0000-01-01", 0.0030), ("2019-06-03", 0.0025), ("2021-01-01", 0.0023),
                              ("2023-01-01", 0.0020), ("2024-01-01", 0.0018), ("2025-01-01", 0.0015),
                              ("2026-01-01", 0.0020))
    cases = {"2018-03-02": 0.0030, "2019-05-31": 0.0030, "2019-06-03": 0.0025, "2020-12-31": 0.0025,
             "2021-01-01": 0.0023, "2024-12-31": 0.0018, "2025-01-02": 0.0015, "2025-12-31": 0.0015,
             "2026-01-01": 0.0020, "2026-11-04": 0.0020}
    for d, r in cases.items():
        assert h1.kr_sell_tax(d) == r, d
    assert h1.stock_sell_tax("us", "2026-01-01") == 0.0


@pytest.mark.parametrize("t,rate", [("2025-12-31", 0.0015), ("2026-01-02", 0.0020)])
def test_T_A1_6_국내_주식_매도세_지수_매도세0_비용(t, rate):
    kr = main.mkt("kr")
    st = h1.new_ledger("kr", "A1", "스프린터", "2025-12-01")
    w = st["wallet"]
    w.cash = 0.0
    w.holdings["KS200"] = Holding(shares=20000.0, avg_price=400.0)
    w.holdings["005930"] = Holding(shares=10, avg_price=70000.0)
    st["positions"]["005930"] = {"buy_price": 70000.0, "days_held": 3, "shares": 10, "buy_date": "2025-12-10"}
    for code, action in (("005930", "매도"), ("000660", "매수")):
        o = {"code": code, "action": action, "signal_date": "2025-12-29", "reason": "손", "note": None}
        st["pending"].append(o)
        st["orders"].append({"id": h1.order_id(o), "signal_date": "2025-12-29", "code": code, "action": action,
                             "reason": "손", "origin": "x", "created_on": "2025-12-29", "status": "pending",
                             "done_date": None, "why": None})
    st["last_date"] = "2025-12-29"
    bar = h1.IdleBar("KS200", t, 401.0, 402.0)
    day = h1.H1Day("kr", "A1", bar, lambda *a: {}, start_date="2025-12-01")
    cache = h1.StrictFrames({"005930": one_row(t, 71000.0), "000660": one_row(t, 150000.0)})
    day.fill(st, "스프린터", 0.20, t, cache, kr, [])
    sell = [f for f in st["fills"] if f["code"] == "005930"][0]
    pr = 71000.0 * (1 - kr.slippage) * 10
    assert sell["tax"] == pr * rate and sell["cash_delta"] == pr - pr * kr.fee_rate - pr * rate
    assert sell["fee"] == pr * kr.fee_rate and sell["slip_cost"] == 10 * 71000.0 * kr.slippage
    fund = [f for f in st["fills"] if f["kind"] == "idle" and f["side"] == "sell"][0]
    assert fund["tax"] == 0.0
    p2 = 401.0 * (1 - kr.slippage) * fund["qty"]
    assert fund["cash_delta"] == p2 - p2 * kr.fee_rate
    buy = [f for f in st["fills"] if f["code"] == "000660"][0]
    E = 150000.0 * (1 + kr.slippage)
    assert buy["cash_delta"] == -(E * buy["qty"] + E * buy["qty"] * kr.fee_rate) and buy["tax"] == 0.0
    # 지갑의 기본 매도세(0.20%)는 바뀌지 않았다
    assert w.sell_tax_rate == kr.sell_tax_rate


def test_T_A1_6_미국_지수_다리_비용(sc_a):
    st = sc_a.states["A1"]["마라토너"]
    for f in st["fills"]:
        if f["kind"] != "idle":
            continue
        E = f["price"] * (1 + SLIP) if f["side"] == "buy" else f["price"] * (1 - SLIP)
        assert f["fee"] == E * f["qty"] * FEE and f["tax"] == 0.0


# ======================= T-A1-7 (저장·읽기) =======================

def test_T_A1_7_저장_읽기_float_hex_정수_주식(sc_a):
    for arm in h1.ARMS:
        for t in h1.TRAINERS:
            st = sc_a.states[arm][t]
            blob = json.dumps(h1.ledger_to_json(st, "us"), ensure_ascii=False, allow_nan=False)
            back = h1.ledger_from_json(json.loads(blob), "us", arm, t)
            for code, h in st["wallet"].holdings.items():
                hb = back["wallet"].holdings[code]
                if code == "SPY":
                    assert isinstance(hb.shares, float) and hb.shares.hex() == h.shares.hex()
                else:
                    assert type(hb.shares) is int and hb.shares == h.shares
            assert h1.ledger_fingerprint({arm: {t: back}}) == h1.ledger_fingerprint({arm: {t: st}})
    assert h1.fmt_units(74.21876543210987) == "74.218765"
    assert typing.get_type_hints(Holding)["shares"] is float


def test_T_A1_7_엄격_읽기(sc_a):
    st = sc_a.states["A1"]["마라토너"]
    good = json.loads(json.dumps(h1.ledger_to_json(st, "us")))
    for bad in (
        {**good, "schema": "v1-usd-1"},
        {k: v for k, v in good.items() if k != "days"},
        {**good, "extra": 1},
        {**good, "wallet": {**good["wallet"], "currency": "KRW"}},
        {**good, "wallet": {**good["wallet"], "holdings": {"SPY": {"shares": 1.0, "avg_price": 1.0, "x": 1}}}},
        {**good, "h1": {**good["h1"], "arm": "A0"}},
        {**good, "stopped": "no"},
    ):
        with pytest.raises(h1.H1LogicError) as e:
            h1.ledger_from_json(bad, "us", "A1", "마라토너")
        assert e.value.code == "L24"
    with pytest.raises(h1.H1LogicError):
        h1.ledger_from_json(good, "kr")


# ======================= T-A1-8 =======================

def test_T_A1_8_A0_는_지수_체결_보유_0(sc_a):
    for t in h1.TRAINERS:
        st = sc_a.states["A0"][t]
        assert "SPY" not in st["wallet"].holdings
        assert not [f for f in st["fills"] if f["kind"] == "idle"]
        assert all(r["idle_units"] == 0 and r["idle_value"] == 0 for r in st["days"])
        a1 = sc_a.states["A1"][t]
        assert [f for f in a1["fills"] if f["kind"] == "idle"]          # A1 은 있다(대조)


# ======================= T-SIG =======================

def test_T_SIG_신호_t_체결_t1_시가(sc_a):
    w = sc_a.world
    n = 0
    for arm in h1.ARMS:
        for t in h1.TRAINERS:
            st = sc_a.states[arm][t]
            orders = {o["id"]: o for o in st["orders"]}
            for f in st["fills"]:
                if f["kind"] != "stock":
                    continue
                o = orders[f["order_id"]]
                assert f["date"] == w.at(o["signal_date"], 1) and f["price"] == w.open(f["code"], f["date"])
                n += 1
    assert n >= 20


# ======================= T-F2 =======================

def test_T_F2_새_장부_총액_몫():
    for mk, total in (("us", 100_000), ("kr", 100_000_000)):
        states = h1.new_ledgers(mk, "2026-02-02")
        assert set(states) == {"A0", "A1"}
        for arm in h1.ARMS:
            got = {t: states[arm][t]["start_cash"] for t in h1.TRAINERS}
            assert got == {"마라토너": total * 0.6, "스프린터": total * 0.3, "파이오니어": total * 0.1}
            for t in h1.TRAINERS:
                st = states[arm][t]
                assert st["wallet"].cash == st["start_cash"] and st["wallet"].currency == main.mkt(mk).currency
                assert st["h1"]["idle_mode"] == ("cash" if arm == "A0" else "index")
                assert st["h1"]["idle_code"] == ("SPY" if mk == "us" else "KS200")


def _plan_f2(D):
    return {"스프린터": {"buy": [(c, D[0]) for c in ("AAA", "BBB", "CCC", "DDD", "EEE", "GGG", "HHH")]},
            "마라토너": {"buy": [(c, D[0]) for c in ("AAA", "BBB", "CCC", "DDD", "EEE", "GGG", "HHH")]}}


def test_T_F2_확신도_hold_veto_MAX_POSITIONS(tmp_path):
    ask = hs.FakeAsk({
        # 스프린터·마라토너 같은 종목은 트레이너마다 따로 물으므로 답도 같은 표를 쓴다
        "AAA": ("buy", 0.5),        # 경계 → 통과
        "BBB": ("buy", 0.49),       # 낮음 → 보류
        "CCC": ("buy", None),       # 무의견 → 통과(0 으로 정렬)
        "DDD": ("buy", "0.7"),      # 문자열 확신도 → 0.7
        "EEE": ("hold", 0.9),       # hold → 보류
        "GGG": ("veto", 0.9),       # veto → 빠짐
        "HHH": ("buy", 0.95),
    })
    sc = hs.scenario(hs.world_a(), hs.S_A, _plan_f2, tmp_path / "log.jsonl", upto=1, ask=ask)
    D0, D1 = sc.D[0], sc.D[1]
    for arm in h1.ARMS:
        st = sc.runner.results[0].states[arm]["스프린터"]
        row = st["days"][0]
        eff = {e["code"]: e["effect"] for e in row["leader"]}
        assert eff == {"AAA": "ordered", "BBB": "low_conv", "CCC": "ordered", "DDD": "ordered", "EEE": "hold",
                       "GGG": "veto", "HHH": "ordered"}
        # 확신도 높은 순(같으면 스크리너 순서): HHH .95, DDD .7, AAA .5, CCC None(0)
        assert [o["code"] for o in st["orders"]] == ["HHH", "DDD", "AAA", "CCC"]
        assert {(s["code"], s["kind"]) for s in st["skips"]} == {("BBB", "확신도낮음"), ("EEE", "팀장hold")}
        assert row["over_slots"] == 0
        # 다음 날: 4개 체결(수량 = 시작 예산 기준 상한), 새 후보 없음
        st1 = sc.runner.results[1].states[arm]["스프린터"]
        assert len(st1["positions"]) == 4
        for f in fills_on(st1, D1, kind="stock"):
            assert f["qty"] == shares_within_cap(30000.0, 0.20, f["price"], FEE, SLIP)
    # 빈자리 부족: 마라토너 후보 7개 중 hold/veto/낮음 빼고 4개 → 5칸 안 → 모두 주문, over_slots 0
    m = sc.runner.results[0].states["A0"]["마라토너"]["days"][0]
    assert sum(e["effect"] == "ordered" for e in m["leader"]) == 4


def test_T_F2_빈자리_부족과_대기_매수도_센다(tmp_path):
    def plan(D):
        return {"스프린터": {"buy": [(c, D[0]) for c in ("AAA", "BBB", "CCC", "DDD", "EEE", "GGG")]
                         + [("HHH", D[0]), ("III", D[1])]}}
    sc = hs.scenario(hs.world_a(), hs.S_A, plan, tmp_path / "log.jsonl", upto=1, leader_mode="replay")
    for arm in h1.ARMS:
        st0 = sc.runner.results[0].states[arm]["스프린터"]
        row = st0["days"][0]
        assert sum(e["effect"] == "ordered" for e in row["leader"]) == 5 and row["over_slots"] == 2
        assert len(st0["pending"]) == 5
        st1 = sc.runner.results[1].states[arm]["스프린터"]
        assert len(st1["positions"]) == 5 and st1["days"][1]["leader"] == []     # 꽉 차서 III 는 묻지도 않음
    # 같은 날 마라토너(후보 없음)는 하루 기록만
    assert sc.runner.results[0].states["A1"]["마라토너"]["days"][0]["leader"] == []


# ======================= T-F5 =======================

def test_T_F5a_호출마다_다른_답이어도_두_장부_같은_판정(tmp_path):
    verdicts = ("buy", "hold", "veto", "buy")
    ask = hs.FakeAsk(per_call=lambda n, code: (verdicts[n % 4], 0.6 + n / 100))
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=4, ask=ask)
    log = sc.runner.log
    for t in h1.TRAINERS:
        a0, a1 = sc.states["A0"][t], sc.states["A1"][t]
        for r0, r1 in zip(a0["days"], a1["days"]):
            assert r0["leader"] == r1["leader"]
            for e in r0["leader"]:
                assert log.get(e["key"])["verdict"] == e["verdict"]
    assert h1_check.errors(h1_check.check_pair("us", sc.states["A0"], sc.states["A1"], log)) == []


def _leader(tmp_path, mode="llm", ask=None, now=None, date="2026-02-02", market="us"):
    log = h1.DecisionLog(tmp_path / "analyst_cache.jsonl")
    clock = now or (lambda: hs.evening(market, date))
    return h1.Leader(market, date, log, mode, now=clock, ask=ask, cli_version="9.9.9"), log


def C(*codes):
    return [{"code": c, "price": 1.0, "rsi": None, "date": "2026-02-02", "reason": f"신호 {c}"} for c in codes]


def test_T_F5b_기록에_없는_후보만_한_번에_묻는다(tmp_path):
    ask = hs.FakeAsk()
    ld, log = _leader(tmp_path, ask=ask)
    ld("마라토너", C("X", "Y"))
    ld("마라토너", C("Y", "Z"))          # A1 자리: A0 에 없던 Z 만
    ld("마라토너", C("X", "Z"))          # 다 있음 → 0번
    ld("스프린터", C("X"))               # 트레이너가 다르면 다른 열쇠
    assert ask.calls == [("마라토너", ["X", "Y"]), ("마라토너", ["Z"]), ("스프린터", ["X"])]
    assert ld.llm_calls == 3 and len(log) == 4
    assert [r["call_id"] for r in log.records()] == ["us|2026-02-02|마라토너|1"] * 2 + ["us|2026-02-02|마라토너|2",
                                                                                  "us|2026-02-02|스프린터|1"]
    assert log.records()[0]["batch"] == ["X", "Y"] and log.records()[0]["cli_version"] == "9.9.9"


def test_T_F5b_봉마다_호출_수_같은_봉_다시는_0번(sc_a, tmp_path):
    # 시나리오 A: 봉마다 후보가 있는 트레이너 수만큼만(A1 은 A0 와 후보가 같아 0번)
    per_bar = [r.llm_calls for r in sc_a.runner.results]
    with_cands = [sum(1 for t in h1.TRAINERS
                      if r.states["A0"][t]["days"][-1]["leader"]) for r in sc_a.runner.results]
    assert per_bar == with_cands and sum(per_bar) == len(sc_a.ask.calls)
    # 커밋 전에 꺼진 상황: 같은 판정 기록으로 같은 봉을 처음부터 다시 → LLM 0번, 결과 지문 같음
    k = 3
    first = sc_a.runner.results[k]
    states_before = sc_a.runner.results[k - 1].states
    n0 = len(sc_a.ask.calls)
    again = sc_a.bar(sc_a.D[k], states=hs.roundtrip(states_before, "us"))
    assert len(sc_a.ask.calls) == n0 and again.llm_calls == 0 and again.new_records == []
    assert again.ok and again.fingerprint == first.fingerprint


@pytest.mark.parametrize("status", ["no_claude", "timeout", "os_error", "nonzero_exit", "decode_error", "bad_json"])
def test_T_F5c_폴백_상태는_규칙_그대로(tmp_path, status):
    ask = hs.FakeAsk(status=status)
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=1, ask=ask)
    recs = sc.runner.log.records()
    assert recs and all(r["status"] == status and r["source"] == "fallback" and r["verdict"] is None for r in recs)
    res = sc.runner.results[1]
    assert any(p.code == "W3" for p in res.problems)
    # 팀장 부재 → 규칙 그대로: HHH(veto 였던 것)·III·JJJ 도 주문
    for arm in h1.ARMS:
        assert {o["code"] for o in sc.states[arm]["마라토너"]["orders"]} >= {"CCC", "HHH"}
        assert {o["code"] for o in sc.states[arm]["스프린터"]["orders"]} >= {"III", "JJJ"}


def test_T_F5c_답에서_빠진_종목은_missing_in_reply(tmp_path):
    ask = hs.FakeAsk({"BBB": None, "AAA": ("buy", 0.3)})
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=0, ask=ask)
    log = sc.runner.log
    b = log.get("us|2026-02-02|마라토너|BBB")
    a = log.get("us|2026-02-02|마라토너|AAA")
    assert b["status"] == "missing_in_reply" and b["source"] == "fallback" and b["verdict"] is None
    assert a["status"] == "ok" and a["source"] == "llm" and a["conviction"] == 0.3 and a["conviction_raw"] == 0.3
    for arm in h1.ARMS:
        eff = {e["code"]: e["effect"] for e in sc.states[arm]["마라토너"]["days"][0]["leader"]}
        assert eff == {"AAA": "low_conv", "BBB": "ordered"}          # 빠진 종목 → 규칙 그대로 통과


def test_T_F5d_글자_정리는_H1_에서만(sc_a, tmp_path):
    D1 = sc_a.D[1]
    log = sc_a.runner.log
    h = log.get(f"us|{D1}|마라토너|HHH")
    j = log.get(f"us|{D1}|스프린터|JJJ")
    assert (h["verdict"], h["verdict_raw"]) == ("veto", " VETO") and (j["verdict"], j["verdict_raw"]) == ("hold", "Hold")
    for arm in h1.ARMS:
        m = sc_a.runner.results[1].states[arm]["마라토너"]
        s = sc_a.runner.results[1].states[arm]["스프린터"]
        assert {e["code"]: e["effect"] for e in m["days"][1]["leader"]} == {"CCC": "ordered", "HHH": "veto"}
        assert "HHH" not in {o["code"] for o in m["orders"]}
        assert {(x["code"], x["kind"]) for x in s["skips"]} == {("III", "확신도낮음"), ("JJJ", "팀장hold")}
    # 운영 analyst.apply 는 그대로 (" VETO" 를 veto 로 보지 않음)
    kept = analyst.apply([{"code": "HHH"}], {"HHH": {"verdict": " VETO", "conviction": 0.9}})
    assert [c["code"] for c in kept] == ["HHH"]


# ======================= T-JSONL (DecisionLog) =======================

def _rec(key, **kw):
    return {"key": key, "status": "ok", **kw}


def test_T_JSONL_추가전용_줄마다_fsync(tmp_path, monkeypatch):
    calls = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (calls.append(fd), real(fd))[1])
    p = tmp_path / "h1" / "analyst_cache.jsonl"
    log = h1.DecisionLog(p)
    assert len(log) == 0 and log.prefix_digest() == (0, h1.hashlib.sha256(b"").hexdigest())
    log.append([_rec("a"), _rec("b"), _rec("c")])
    assert len(calls) >= 3                                  # 줄마다 fsync (+ 새 파일이면 폴더)
    lines = p.read_bytes().split(b"\n")
    assert len(lines) == 4 and lines[-1] == b""
    n1, d1 = log.prefix_digest()
    log.append([_rec("d")])
    assert log.prefix_digest(n1) == (n1, d1)               # 앞부분 지문은 그대로
    back = h1.DecisionLog(p)
    assert [r["key"] for r in back.records()] == ["a", "b", "c", "d"] and back.truncated is None
    assert back.prefix_digest() == log.prefix_digest()
    with pytest.raises(h1.H1LogicError) as e:
        back.append([_rec("e"), _rec("a")])                 # 이미 있는 열쇠 → 아무것도 안 씀
    assert e.value.code == "L18" and len(h1.DecisionLog(p)) == 4


def test_T_JSONL_반쯤_쓴_마지막_줄은_잘라냄(tmp_path):
    p = tmp_path / "log.jsonl"
    h1.DecisionLog(p).append([_rec("a"), _rec("b")])
    good = p.read_bytes()
    p.write_bytes(good + b'{"key": "c", "sta')
    log = h1.DecisionLog(p)
    assert [r["key"] for r in log.records()] == ["a", "b"]
    assert log.truncated["bytes"] == len(b'{"key": "c", "sta') and p.read_bytes() == good
    log.append([_rec("c")])
    assert [r["key"] for r in h1.DecisionLog(p).records()] == ["a", "b", "c"]


def test_T_JSONL_중간_줄_깨짐_중복_열쇠(tmp_path):
    p = tmp_path / "log.jsonl"
    p.write_bytes(b'{"key":"a"}\n{"key": broken}\n{"key":"c"}\n')
    with pytest.raises(h1.H1LogicError) as e:
        h1.DecisionLog(p)
    assert e.value.code == "L24"
    p.write_bytes(b'{"key":"a"}\n{"key":"a"}\n')
    with pytest.raises(h1.H1LogicError) as e:
        h1.DecisionLog(p)
    assert e.value.code == "L18"


def test_T_JSONL_지난_줄_수정은_L18(tmp_path):
    p = tmp_path / "log.jsonl"
    log = h1.DecisionLog(p)
    log.append([_rec("a", verdict="buy"), _rec("b")])
    head = log.prefix_digest()
    assert h1_check.check_decisions("us", h1.DecisionLog(p), head) == []
    p.write_bytes(p.read_bytes().replace(b'"buy"', b'"veto"'))
    probs = h1_check.check_decisions("us", h1.DecisionLog(p), head)
    assert [x.code for x in probs] == ["L18"]
    p.write_bytes(b'{"key":"a"}\n')                         # 줄이 사라짐
    assert [x.code for x in h1_check.check_decisions("us", h1.DecisionLog(p), head)] == ["L18"]


def test_T_JSONL_판정은_장부보다_먼저_디스크에(sc_a):
    """run_bar 가 끝나기 전에(장부 저장 전) 판정 기록 파일에 이미 그 봉의 줄이 있다."""
    p = sc_a.runner.log.path
    on_disk = [json.loads(x) for x in p.read_bytes().splitlines()]
    assert [r["key"] for r in on_disk] == [r["key"] for r in sc_a.runner.log.records()]
    for res in sc_a.runner.results:
        for r in res.new_records:
            assert r["key"] in {x["key"] for x in on_disk}


# ======================= T-LLMTIME (Leader) =======================

def test_T_LLMTIME_next_open():
    assert h1.next_open("kr", "2026-11-04") == datetime(2026, 11, 5, 9, 0, tzinfo=KST)
    assert h1.next_open("kr", "2026-11-06") == datetime(2026, 11, 9, 9, 0, tzinfo=KST)        # 금 → 월
    assert h1.next_open("us", "2026-11-06") == datetime(2026, 11, 9, 9, 30, tzinfo=ET)
    # 서머타임(2026-03-08 시작): 목 → 금 09:30 EST(UTC−5), 금 → 월 09:30 EDT(UTC−4)
    assert h1.next_open("us", "2026-03-05").utcoffset().total_seconds() == -5 * 3600
    assert h1.next_open("us", "2026-03-06") == datetime(2026, 3, 9, 9, 30, tzinfo=ET)
    assert h1.next_open("us", "2026-03-06").utcoffset().total_seconds() == -4 * 3600


@pytest.mark.parametrize("market,now,mode", [
    ("kr", datetime(2026, 2, 5, 8, 59, tzinfo=KST), "llm"),
    ("kr", datetime(2026, 2, 5, 10, 0, tzinfo=KST), "late"),
    ("us", datetime(2026, 2, 5, 9, 29, tzinfo=ET), "llm"),
    ("us", datetime(2026, 2, 5, 9, 31, tzinfo=ET), "late"),
    ("us", datetime(2026, 2, 5, 23, 29, tzinfo=KST), "llm"),   # 한국 시각으로 줘도 같은 순간
    ("us", datetime(2026, 2, 5, 23, 31, tzinfo=KST), "late"),
])
def test_T_LLMTIME_장_시작_전에만_llm(tmp_path, market, now, mode):
    """봉 2026-02-04 를 처리. 다음 장 시작 = 2026-02-05 국내 09:00 KST / 미국 09:30 ET."""
    codes = ("005930", "000660") if market == "kr" else ("AAA", "BBB")
    w = hs.World(market, codes)
    S = "2026-02-04"
    ask = hs.FakeAsk()
    brains = hs.fake_brains({"마라토너": {"buy": [(codes[0], S)]}})
    r = hs.Runner(w, S, tmp_path / "log.jsonl", leader_mode="llm", ask=ask, clock=lambda: now, brains=brains)
    with hs.brains_patched(brains):
        res = r.step(S)
    assert res.mode == mode and res.late == (mode == "late")
    row = res.states["A0"]["마라토너"]["days"][0]
    assert row["late"] == (mode == "late") and row["mode"] == mode
    if mode == "llm":
        assert len(ask.calls) == 1 and r.log.records()[0]["status"] == "ok"
    else:
        assert ask.calls == [] and r.log.records()[0]["status"] == "late_no_llm"
        assert any(p.code == "W1" for p in res.problems)
    assert r.log.records()[0]["next_open"] == h1.next_open(market, S).isoformat()


def test_T_LLMTIME_묻기_직전마다_시각_재확인(tmp_path):
    """봉 시작은 장 시작 전(llm)이었는데 첫 호출이 오래 걸려 장이 열림 → 다음 호출부터 late_no_llm."""
    t = hs.S_A
    clock = SimpleNamespace(now=datetime(2026, 2, 3, 9, 0, tzinfo=ET))
    ask = hs.FakeAsk(clock_after=lambda: setattr(clock, "now", datetime(2026, 2, 3, 9, 31, tzinfo=ET)))
    w = hs.world_a()
    brains = hs.fake_brains(hs.plan_a([w.at(t, k) for k in range(8)]))
    r = hs.Runner(w, t, tmp_path / "log.jsonl", leader_mode="llm", ask=ask, clock=lambda: clock.now, brains=brains)
    with hs.brains_patched(brains):
        res = r.step(t)
    assert res.mode == "llm" and not res.late
    assert ask.calls == [("마라토너", ["AAA", "BBB"])] and res.llm_calls == 1 and res.late_calls == 1
    st = {r_["key"].split("|")[2] + "|" + r_["code"]: r_["status"] for r_ in r.log.records()}
    assert st == {"마라토너|AAA": "ok", "마라토너|BBB": "ok", "스프린터|AAA": "late_no_llm",
                  "스프린터|BBB": "late_no_llm", "스프린터|CCC": "late_no_llm"}
    for arm in h1.ARMS:
        days = {tn: res.states[arm][tn]["days"][0] for tn in h1.TRAINERS}
        assert days["스프린터"]["late_calls"] == (1 if arm == "A0" else 0) and days["마라토너"]["late_calls"] == 0
        assert all(d["late"] is False and d["mode"] == "llm" for d in days.values())


def test_Leader_mode_replay_는_묻지_않음(tmp_path):
    ask = hs.FakeAsk()
    ld, log = _leader(tmp_path, mode="replay", ask=ask)
    assert ld("마라토너", C("X")) == {} and ask.calls == []
    assert log.records()[0]["status"] == "replay_no_llm" and log.records()[0]["source"] == "fallback"
    with pytest.raises(ValueError):
        h1.Leader("us", "2026-02-02", log, "online")


def test_Leader_note_500자_확신도_원래값(tmp_path):
    ask = hs.FakeAsk()
    ld, log = _leader(tmp_path, ask=ask)
    ask.answers = {"X": ("BUY\n", "0.7")}
    out = ld("마라토너", C("X"))
    rec = log.records()[0]
    assert out == {"X": {"code": "X", "verdict": "buy", "conviction": 0.7, "note": "가짜 팀장 메모 X"}}
    assert rec["verdict_raw"] == "BUY\n" and rec["conviction_raw"] == "0.7" and rec["signal"]["reason"] == "신호 X"


# ======================= T-SHADOW =======================

def _close(st, value, *, prev_value=None, t=T2):
    day = h1.H1Day("us", st["h1"]["arm"], h1.IdleBar("SPY", t, 500.0, 500.0), lambda *a: {},
                   start_date="2026-02-02", prev_cal_date=T1)
    w = st["wallet"]
    w.cash = value
    st["prev_value"] = prev_value
    day.close_day(st, st["h1"]["trainer"], t, {"SPY": 500.0}, value)
    return st["days"][-1]


@pytest.mark.parametrize("prev,value", [
    (60000.0, 60000.0 * 0.931), (60000.0, 60000.0 * 0.929),                    # 하루 −6.9% / −7.1%
    (53500.0, 53990.0), (54100.0, 53950.0),                                     # 누적 −10.02% / −10.08%
    (55000.0, 54001.0),                                                         # 누적 −9.998%
])
def test_T_SHADOW_경계와_전날_하루_기록(prev, value):
    st = h1.new_ledger("us", "A0", "마라토너", "2026-02-02")
    st["days"] = [{"date": T1, "value": prev, "events": []}]
    row = _close(st, value, prev_value=12345.0)              # team prev_value 를 일부러 다른 값으로
    want = CircuitBreaker(0.10, 0.07).check(60000.0, prev, value)
    evs = [e for e in row["events"] if e["kind"] == "shadow_breaker"]
    assert (evs[0]["why"] if evs else None) == want
    if want:
        assert evs[0]["first"] is True
    assert st["stopped"] is False and st["pending"] == []


def test_T_SHADOW_S_날은_prev_없음_첫발동_표시():
    st = h1.new_ledger("us", "A0", "마라토너", "2026-02-02")
    row = _close(st, 60000.0 * 0.92, t="2026-02-02")           # 누적 −8%, prev 없음 → 안 걸림
    assert row["events"] == []
    st["days"][-1]["events"] = [{"kind": "shadow_breaker", "why": "x", "first": True}]
    row2 = _close(st, 60000.0 * 0.85, t=T2)
    assert row2["events"][0]["first"] is False


def test_T_SHADOW_폭락_장면_두_장부(tmp_path):
    D2 = "2026-02-04"
    w = hs.world_a(crash={"BBB": (D2, 0.55), "AAA": (D2, 0.55)})
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=3, world=w)
    for arm in h1.ARMS:
        st = sc.states[arm]["마라토너"]
        evs = {r["date"]: r["events"] for r in st["days"] if r["events"]}
        assert D2 in evs and evs[D2][0]["first"] is True and evs[D2][0]["why"].startswith("누적")
        assert all(e[0]["first"] is False for d, e in evs.items() if d != D2)
        assert st["stopped"] is False
        assert not any(o["reason"] == "서킷 브레이커" for o in st["orders"])
    assert h1_check.errors(h1_check.check_ledger("us", "A1", sc.states["A1"], None, sc.runner.log)) == []


# ======================= T-ORDERS =======================

def test_T_ORDERS_상태와_사유(sc_a):
    D = sc_a.D
    st = sc_a.states["A0"]["스프린터"]
    by = {o["id"]: o for o in st["orders"]}
    sell = by[f"{D[2]}|AAA|매도"]
    assert sell["origin"] == "sell_signal" and sell["status"] == "filled" and sell["done_date"] == D[3]
    assert sell["reason"].startswith("가짜 매도 신호 AAA") and len(sell["reason"]) > 14     # 사유 전체
    assert by[f"{D[0]}|AAA|매수"]["status"] == "filled" and by[f"{D[0]}|AAA|매수"]["origin"] == "candidate"
    p = sc_a.states["A0"]["파이오니어"]
    assert {o["code"]: (o["status"], o["why"]) for o in p["orders"]} == {"FFF": ("skipped", "0주"),
                                                                         "GGG": ("filled", None)}
    m = sc_a.states["A1"]["마라토너"]
    assert {o["code"]: o["status"] for o in m["orders"] if o["action"] == "매수"}["DDD"] == "skipped"
    assert all(o["created_on"] == o["signal_date"] for o in m["orders"])


def test_T_ORDERS_이미_보유_매수_보유_없는_매도는_dropped():
    st = hand_state(cash=10000.0, units=0.0, positions={"AAA": (5, 100.0)},
                    pending=[("AAA", "매수"), ("ZZZ", "매도")])
    do_fill(st, prices={"AAA": 101.0, "ZZZ": 50.0})
    assert {o["code"]: (o["status"], o["why"], o["done_date"]) for o in st["orders"]} == {
        "AAA": ("dropped", "이미 보유", T2), "ZZZ": ("dropped", "보유 없음", T2)}
    assert st["pending"] == [] and st["positions"]["AAA"]["shares"] == 5
    assert not [f for f in st["fills"] if f["kind"] == "stock"]


# ======================= T-HALT =======================

def _plan_halt(D):
    return {"스프린터": {"buy": [("005380", D[0])]},
            "파이오니어": {"buy": [("005380", D[0])]},
            "마라토너": {"buy": [("000660", D[0])], "sell": [("000660", D[5]), ("000660", D[7])]}}


def test_T_HALT_국내_3일_정지(tmp_path):
    codes = ("005930", "000660", "005380")
    tmp = hs.World("kr", codes)
    D = [tmp.at("2026-02-02", k) for k in range(10)]
    w = hs.World("kr", codes, bases={"005930": 70000, "000660": 150000, "005380": 200000},
                 halts={"005380": D[1:4], "000660": D[5:7]})
    sc = hs.scenario(w, "2026-02-02", _plan_halt, tmp_path / "log.jsonl", upto=8, leader_mode="replay")
    res = sc.runner.results
    for arm in h1.ARMS:
        for tn in ("스프린터", "파이오니어"):
            st = sc.states[arm][tn]
            f = [x for x in st["fills"] if x["code"] == "005380"]
            assert [(x["date"], x["price"]) for x in f] == [(D[4], w.open("005380", D[4]))]   # 정지 뒤 첫 봉 시가
            for k in (1, 2, 3):
                assert res[k].states[arm][tn]["pending"][0]["code"] == "005380"
                assert "005380" in res[k].states[arm][tn]["days"][k]["halted"]
            if arm == "A1":
                legs = [x for x in st["fills"] if x["kind"] == "idle" and x["side"] == "sell"]
                assert [x["date"] for x in legs] == [D[4]] and legs[0]["purpose"] == "fund:005380"
        # 정지 종목 후보 제외 (스크리너 오래된 봉)
        for k in (1, 2, 3):
            assert all(c["code"] != "005380" for cs in res[k].found.values() for c in cs)
        # 보유 종목 정지: 판단 쉼(D5 매도 신호 무시), 보유일수 그대로, 마지막 종가 평가
        m = sc.states[arm]["마라토너"]
        days = {r["date"]: r for r in m["days"]}
        last_close = w.close("000660", D[4])
        assert days[D[5]]["marks"]["000660"] == last_close and days[D[6]]["marks"]["000660"] == last_close
        held = [res[k].states[arm]["마라토너"]["positions"]["000660"]["days_held"] for k in range(1, 8)]
        assert held == [0, 1, 2, 3, 3, 3, 4]
        sells = [x for x in m["fills"] if x["code"] == "000660" and x["side"] == "sell"]
        assert [x["date"] for x in sells] == [D[8]]                      # D7 신호 → D8, D5 신호는 정지라 없음
    assert any(p.code == "W2" for p in res[1].problems)


# ======================= T-DELIST (엔진 부분) =======================

def _plan_delist(D):
    return {"마라토너": {"buy": [("AAA", D[0])]},
            "스프린터": {"buy": [("AAA", D[0]), ("BBB", D[0])], "sell": [("AAA", D[2])]}}


def test_T_DELIST_정리_a_prime(tmp_path):
    sc = hs.scenario(hs.world_a(), hs.S_A, _plan_delist, tmp_path / "log.jsonl", upto=2, leader_mode="replay")
    D = sc.D
    P = round(sc.world.close("AAA", D[2]) * 0.4, 4)
    reg = {"kind": "delist", "code": "AAA", "last_date": D[2], "last_close": P, "source": "시험"}
    for arm in h1.ARMS:
        for tn in h1.TRAINERS:
            sc.states[arm][tn]["corp_actions"].append(dict(reg))
    sc.runner.delist = {"AAA": {"last_date": D[2], "last_close": P}}
    frames = {c: f for c, f in sc.world.frames.items() if c != "AAA"}    # 상장폐지 종목은 시세를 받지 않음
    res = sc.step(D[3], frames=frames)
    for arm in h1.ARMS:
        for tn in ("마라토너", "스프린터"):
            st = res.states[arm][tn]
            f = [x for x in st["fills"] if x["purpose"] == "delist"]
            assert len(f) == 1 and f[0]["price"] == P and f[0]["date"] == D[3] and f[0]["order_id"] is None
            assert f[0]["qty"] == sc.runner.results[2].states[arm][tn]["positions"]["AAA"]["shares"]
            assert "AAA" not in st["positions"] and "AAA" not in st["wallet"].holdings
            if arm == "A1":                                              # 정리 대금은 같은 시가에 지수로
                assert [x["purpose"] for x in fills_on(st, D[3])] == ["delist", "sweep"]
        sp = res.states[arm]["스프린터"]
        assert {o["id"]: (o["status"], o["why"]) for o in sp["orders"]}[f"{D[2]}|AAA|매도"] == ("dropped", "delist")
    assert res.ok
    # 정리 뒤에도 장부는 이어진다(상장폐지 종목 시세 없이)
    sc.step(D[4], frames=frames)


# ======================= T-FP =======================

def test_T_FP_장부_내용_지문(sc_a):
    base = sc_a.states
    fp = h1.ledger_fingerprint(base)
    meta = hs.roundtrip(base, "us")
    for arm in h1.ARMS:
        for t in h1.TRAINERS:
            st = meta[arm][t]
            st["h1"] = {**st["h1"], "code_hash": "다른 코드", "updated_at": "어제", "restart_no": 7}
            st["wallet"].name = "다른 이름"
            for row in st["days"]:
                row.update(run_at="2030-01-01T00:00:00+09:00", mode="late", late=True, late_calls=9,
                           code_hash="xyz", env={"python": "9"})
    assert h1.ledger_fingerprint(meta) == fp
    # dict 키 순서가 달라도 같음
    shuffled = {arm: {t: dict(reversed(list(meta[arm][t].items()))) for t in reversed(h1.TRAINERS)}
                for arm in reversed(h1.ARMS)}
    assert h1.ledger_fingerprint(shuffled) == fp
    # 체결 수량·현금 1ulp → 다름
    one = hs.roundtrip(base, "us")
    f = [x for x in one["A1"]["마라토너"]["fills"] if x["kind"] == "idle"][0]
    f["qty"] = next_up(f["qty"])
    assert h1.ledger_fingerprint(one) != fp
    two = hs.roundtrip(base, "us")
    two["A0"]["스프린터"]["wallet"].cash = next_up(two["A0"]["스프린터"]["wallet"].cash)
    assert h1.ledger_fingerprint(two) != fp
    with pytest.raises(ValueError):
        bad = hs.roundtrip(base, "us")
        bad["A0"]["스프린터"]["days"][0]["value"] = float("nan")
        h1.ledger_fingerprint(bad)


def next_up(x):
    import math
    return math.nextafter(x, math.inf)


# ======================= T-LOOK =======================

def test_T_LOOK_전체_시세_자른_시세_흔든_미래(sc_a):
    k = 4
    t = sc_a.D[k]
    before = hs.roundtrip(sc_a.runner.results[k - 1].states, "us")
    first = sc_a.runner.results[k]
    cut = {c: h1.cut_frame(f, t) for c, f in sc_a.world.frames.items()}
    again = sc_a.bar(t, states=before, frames=cut)
    assert again.ok and again.fingerprint == first.fingerprint
    # t 의 종가·고가·저가·거래량과 그 뒤 봉을 흔든다 → t 시가 체결·전날까지 기록 그대로
    shaken = {}
    for c, f in sc_a.world.frames.items():
        g = f.copy()
        ts = pd.Timestamp(t)
        for col in ("Close", "High", "Low", "Volume"):
            g.loc[ts, col] = g.loc[ts, col] * 1.37
        later = g.index > ts
        for col in ("Open", "High", "Low", "Close", "Volume"):
            g.loc[later, col] = g.loc[later, col] * 3.1
        shaken[c] = g
    bar = sc_a.world.idle_bar(t)
    res = sc_a.bar(t, states=hs.roundtrip(before, "us"), frames=shaken,
                   idle=h1.IdleBar(bar.code, t, bar.open, bar.close * 1.21))
    assert res.ok
    for arm in h1.ARMS:
        for tn in h1.TRAINERS:
            a, b = res.states[arm][tn], first.states[arm][tn]
            assert fills_on(a, t) == fills_on(b, t)
            assert a["days"][:-1] == b["days"][:-1]
            assert [o["id"] for o in a["orders"]] == [o["id"] for o in b["orders"]]


def test_T_LOOK_진짜_브레인도_자른_시세와_같음(tmp_path):
    """진짜 브레인(지표 포함)으로 여러 봉: 전체 시세로 처리한 결과 == 봉마다 미리 자른 시세로 처리한 결과."""
    w = hs.World("us", ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"))
    S = "2026-02-02"
    a = hs.Runner(w, S, tmp_path / "a.jsonl", leader_mode="replay")
    b = hs.Runner(w, S, tmp_path / "b.jsonl", leader_mode="replay")
    t = S
    for _ in range(12):
        ra = a.step(t)
        rb = b.step(t, frames={c: h1.cut_frame(f, t) for c, f in w.frames.items()})
        assert ra.fingerprint == rb.fingerprint
        t = w.at(t, 1)
    assert h1_check.errors(h1_check.check_ledger("us", "A1", a.states["A1"], w.calendar(S, w.prev(t)), a.log)) == []


# ======================= T-ENTRY =======================

def test_T_ENTRY_team_에_h1_진입점_없음():
    src = (ROOT / "team.py").read_text(encoding="utf-8")
    assert "--h1" not in src and "import h1" not in src and "from h1" not in src


def test_T_ENTRY_운영_경로에서_h1_을_읽지_않는다(tmp_path):
    script = textwrap.dedent(f"""
        import json, sys
        from pathlib import Path
        sys.path.insert(0, {str(ROOT)!r})
        import numpy as np, pandas as pd
        import main, team, screener, analyst
        from risk_guard import CircuitBreaker
        team.STATE_DIR = Path({str(tmp_path)!r})
        idx = pd.bdate_range("2026-06-01", "2026-11-03")
        df = pd.DataFrame({{"Open": np.linspace(100, 110, len(idx)), "High": 111.0, "Low": 99.0,
                           "Close": np.linspace(100.5, 110.5, len(idx)), "Volume": 1e6}}, index=idx)
        main.prices_for = lambda m, code, start: df
        main.load_benchmark = lambda start, mk=None: df
        bar = idx[-1].date().isoformat()
        screener.scan = lambda n=50, market="us": ({{"마라토너": [{{"code": "AAA", "price": 1.0, "date": bar,
                                                                    "rsi": 50.0, "reason": "x"}}]}}, 1)
        analyst.analyze = lambda *a, **k: None
        team.run(5, "us")
        team.run_trainer("스프린터", 3000.0, 0.2, CircuitBreaker(0.1, 0.07),
                         [{{"code": "BBB", "date": bar, "reason": "y"}}], bar, st=None, cache={{}}, mk="us", h1=None)
        print(json.dumps({{"h1": "h1" in sys.modules, "h1_check": "h1_check" in sys.modules,
                           "saved": sorted(p.name for p in Path({str(tmp_path)!r}).glob("team_*.json"))}}))
    """)
    r = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=120,
                       cwd=str(tmp_path))
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out == {"h1": False, "h1_check": False, "saved": ["team_마라토너.json", "team_스프린터.json"]}


def test_G0_h1_이_있으면_st_필수():
    day = h1.H1Day("us", "A0", h1.IdleBar("SPY", T2, 1.0, 1.0), lambda *a: {}, start_date="2026-02-02")
    with pytest.raises(ValueError):
        team.run_trainer("마라토너", 6000.0, 0.3, CircuitBreaker(*h1.LEDGER_BREAKER), [], T2, st=None, cache={},
                         mk="us", h1=day)


def test_엄격_시세_묶음():
    sf = h1.StrictFrames({"AAA": None})
    assert "ZZZ" in sf and sf["AAA"] is None
    with pytest.raises(h1.H1LogicError):
        sf["ZZZ"]
    assert team._prices("AAA", sf) is None                       # 인터넷으로 받으러 가지 않음


def test_상수와_규칙값():
    assert h1.SHADOW_BREAKER == (0.10, 0.07) and h1.LEDGER_BREAKER == (float("inf"), float("inf"))
    assert h1.SWEEP_SHRINK == (1e-12, 1e-9, 1e-6) and h1.SWEEP_MIN == 1.0 and h1.SHORT_MARGIN == 1e-9
    assert "h1_check.py" in h1.CODE_FILES and "prompts/파이오니어.md" in h1.CODE_FILES
    for f in h1.CODE_FILES:
        if f not in ("h1_report.py", "h1_replay.py"):          # 단계 4·5 에서 생김
            assert (ROOT / f).exists(), f
    r = h1.rule_constants("kr")
    assert r["eps_cash"] == 1e-6 and r["eps_rel"] == 1e-9 and r["idle_code"] == "KS200"
    assert r["stock_sell_tax"][0] == ["0000-01-01", 0.003] and r["ledger_breaker"] == "off"
    json.dumps(r, allow_nan=False)
    assert h1.decision_key("us", "2026-11-09", "마라토너", "AAPL") == "us|2026-11-09|마라토너|AAPL"
    assert h1.idle_code("us") == "SPY" and h1.idle_code("kr") == "KS200"


def test_h1_은_주문_모듈을_읽지_않는다():
    for f in ("h1.py", "h1_check.py"):
        src = (ROOT / f).read_text(encoding="utf-8")
        assert "order_runner" not in src and "import broker" not in src and "from broker" not in src


def test_run_bar_거절_조건(sc_a):
    t = sc_a.D[8]
    with pytest.raises(h1.H1PreconditionError):          # 이미 처리한 봉 → 사전 조건(L 아님)
        sc_a.bar(sc_a.D[7])
    with pytest.raises(h1.H1PreconditionError):          # 앞 거래일이 장부 last_date 와 다름(빠진 봉)
        sc_a.bar(sc_a.D[9], prev_cal_date=sc_a.D[8])
    assert issubclass(h1.H1PreconditionError, ValueError) and not issubclass(h1.H1PreconditionError, h1.H1LogicError)
    frames = {c: (f[f.index != pd.Timestamp(t)] if c == "BBB" else f) for c, f in sc_a.world.frames.items()}
    with pytest.raises(h1.H1DataProblem) as e:           # 보유 종목 t 행 없음(정지 아님) → D3
        sc_a.bar(t, frames=frames)
    assert e.value.kind == "D3" and e.value.exit_code == 4
    with pytest.raises(h1.H1DataProblem) as e:
        sc_a.bar(t, frames={c: (None if c == "BBB" else f) for c, f in sc_a.world.frames.items()})
    assert e.value.kind == "D2"


# ======================= R2 식 대조 =======================

class R2Sleeve:
    def __init__(self, wallet, start_cash, cap, positions):
        self.wallet, self.start_cash, self.cap, self.cap_budget = wallet, start_cash, cap, start_cash
        self.positions = {c: {"shares": p["shares"]} for c, p in positions.items()}

    def units(self, idx_code):
        h = self.wallet.holdings.get(idx_code)
        return float(h.shares) if h else 0.0


class R2Ref:
    """origin/research-r2-2026-11-04 reports/research-r2-2026-11-04/sim_team.py 의 시가 메서드를 글자 그대로 옮긴 것
    (_sell 444~465, _buy 467~480, _idx_net_per_unit 482~485, _raise_cash 492~500, _sweep_to_index 502~513,
    _open 520~546 의 순서, _fill_sell 556~562, _fill_buy 567~603, OperatingStartSim(설계 §5.1-3)의 S+1 첫 전부 지수).
    md·t 는 그날 값(idx_open, date, tax)으로 바꿨다. 기록은 비교용으로 체결 뒤 현금을 더 적는다."""

    def __init__(self, idx_code, idx_open, date, tax):
        self.idx_code, self.idx_open, self.date, self.tax = idx_code, idx_open, date, tax
        self.fills, self.skips = [], []

    def _sell(self, s, code, px, qty, tax, kind):
        w = s.wallet
        before, keep = w.cash, w.sell_tax_rate
        w.sell_tax_rate = tax
        ok = w.sell(code, px, qty, self.date)
        w.sell_tax_rate = keep
        if not ok:
            raise AssertionError(f"{code} 매도 실패 qty={qty}")
        net = w.cash - before
        self.fills.append(("idle" if kind == "index" else "stock", "sell", code, hx(qty), px, hx(w.cash)))
        return net

    def _buy(self, s, code, px, qty, kind):
        w = s.wallet
        if not w.buy(code, px, qty, self.date):
            return False
        self.fills.append(("idle" if kind == "index" else "stock", "buy", code, hx(qty), px, hx(w.cash)))
        return True

    def _idx_net_per_unit(self, s):
        w, px = s.wallet, self.idx_open
        proceeds = px * (1 - w.slippage)
        return proceeds - proceeds * w.fee_rate

    def _raise_cash(self, s, need):
        short = need - s.wallet.cash
        if short <= 0:
            return
        held = s.units(self.idx_code)
        u = min(held, short / self._idx_net_per_unit(s) * (1 + 1e-9))
        if u > 0:
            self._sell(s, self.idx_code, self.idx_open, u, 0.0, "index")

    def _sweep_to_index(self, s):
        w = s.wallet
        if w.cash < 1.0:
            return
        px = self.idx_open
        unit = px * (1 + w.slippage) * (1 + w.fee_rate)
        for shrink in (1e-12, 1e-9, 1e-6):
            u = w.cash / unit * (1 - shrink)
            if self._buy(s, self.idx_code, px, u, "index"):
                return
        raise AssertionError("지수 매수 실패")

    def _fill_sell(self, s, o, px):
        pos = s.positions.pop(o["code"])
        self._sell(s, o["code"], px, pos["shares"], self.tax, "stock")

    def _fill_buy(self, s, o, px, mode):
        w = s.wallet
        budget = s.cap_budget
        cap = s.cap * 1.0
        n = shares_within_cap(budget, cap, px, w.fee_rate, w.slippage)
        if n <= 0:
            self.skips.append((o["code"], "0주"))
            return
        exec_px = px * (1 + w.slippage)
        need = exec_px * n + exec_px * n * w.fee_rate
        avail = w.cash
        if mode == "index":
            avail += s.units(self.idx_code) * self._idx_net_per_unit(s)
        short_of_cash = need > avail * (1 - 1e-9) if mode == "index" else need > avail
        if short_of_cash:
            self.skips.append((o["code"], "현금부족"))
            return
        if mode == "index":
            self._raise_cash(s, need)
        if not self._buy(s, o["code"], px, n, "stock"):
            self.skips.append((o["code"], "현금부족"))
            return
        s.positions[o["code"]] = {"shares": n}

    def open(self, s, todo, mode, start=False):
        if start and mode == "index":
            self._sweep_to_index(s)
        for o, px in todo:
            if o["action"] == "매도" and o["code"] in s.positions:
                self._fill_sell(s, o, px)
        for o, px in todo:
            if o["action"] == "매수" and o["code"] not in s.positions:
                self._fill_buy(s, o, px, mode)
        if mode == "index":
            self._sweep_to_index(s)


def _r2_compare(sc, k, arm, tname):
    """처리 전 장부(k−1)를 R2 식으로 하루 시가 처리 → h1 의 k 처리 결과와 비트까지 비교."""
    w = sc.world
    t = sc.D[k]
    before = hs.roundtrip(sc.runner.results[k - 1].states, w.market)[arm][tname]
    after = sc.runner.results[k].states[arm][tname]
    s = R2Sleeve(before["wallet"], before["start_cash"], main.CONFIG["종목상한"][tname], before["positions"])
    ref = R2Ref(w.idle_code, w.idle_bar(t).open, t, 0.0)
    todo = [(o, w.open(o["code"], t)) for o in before["pending"]]
    ref.open(s, todo, "index" if arm == "A1" else "cash", start=(k == 1))
    got = [(f["kind"], f["side"], f["code"], hx(f["qty"]), f["price"], hx(f["cash_after"])) for f in fills_on(after, t)]
    assert got == ref.fills, (arm, tname, t)
    assert hx(s.wallet.cash) == hx(after["wallet"].cash)
    assert {c: hx(h.shares) for c, h in s.wallet.holdings.items()} == \
           {c: hx(h.shares) for c, h in after["wallet"].holdings.items()}
    assert sorted(ref.skips) == sorted((x["code"], x["kind"]) for x in after["skips"]
                                       if x["date"] == t and x["kind"] in ("0주", "현금부족"))
    return len(ref.fills)


def test_R2_식_대조_A1_매도1_매수2_쓸어담기(tmp_path):
    """A1 스프린터의 한 날(매도 1·매수 2·쓸어 담기): AAA 가 오른 장면에서 h1 == R2 시가 메서드(비트까지)."""
    w = hs.world_a(crash={"AAA": ("2026-02-04", 2.5)})
    sc = hs.scenario_a(tmp_path / "log.jsonl", upto=3, world=w)
    n = _r2_compare(sc, 3, "A1", "스프린터")
    kinds = [(f["kind"], f["side"], f["purpose"]) for f in fills_on(sc.states["A1"]["스프린터"], sc.D[3])]
    assert kinds == [("stock", "sell", "order"), ("stock", "buy", "order"), ("stock", "buy", "order"),
                     ("idle", "buy", "sweep")] and n == 4


def test_R2_식_대조_시나리오_A_모든_날_모든_장부(sc_a):
    """S+1(첫 전부 지수, OperatingStartSim) 부터 모든 날 · A0·A1 · 트레이너 3명: h1 시가 결과 == R2 식."""
    total = 0
    for k in range(1, len(sc_a.runner.results)):
        for arm in h1.ARMS:
            for tn in h1.TRAINERS:
                total += _r2_compare(sc_a, k, arm, tn)
    assert total >= 30


# ======================= R14: 평가 가격표 =======================

def copy_state(st):
    blob = json.dumps(h1.ledger_to_json(st, "us"), ensure_ascii=False)
    return h1.ledger_from_json(json.loads(blob), "us")


def _r14_day():
    return h1.H1Day("us", "A1", h1.IdleBar("SPY", T2, 500.0, 501.0), lambda *a: {}, start_date="2026-02-02",
                    prev_cal_date=T1)


def test_R14_가격표에_보유_종목이_빠지면_L7():
    """평가 가격표 문제는 예외 대신 L7 로 적고 하루 기록은 남긴다(2b-1 검토 B-3)."""
    st = hand_state(arm="A1", cash=0.5, units=10.0, positions={"AAA": (5, 100.0)})
    w = st["wallet"]
    for prices, value in (({"SPY": 501.0}, w.value({"SPY": 501.0})),                     # 주식 가격 없음(R14)
                          ({"SPY": 499.0, "AAA": 101.0}, w.value({"SPY": 499.0, "AAA": 101.0})),   # 지수 종가 다름
                          ({"SPY": 501.0, "AAA": 101.0}, 1.0)):                          # 평가액이 다름
        s2 = copy_state(st)
        day = _r14_day()
        day.close_day(s2, "스프린터", T2, prices, value)
        assert "L7" in {p.code for p in day.problems} and len(s2["days"]) == 1
    day = _r14_day()
    day.close_day(st, "스프린터", T2, {"SPY": 501.0, "AAA": 101.0}, w.value({"SPY": 501.0, "AAA": 101.0}))
    assert day.problems == []
    row = st["days"][-1]
    assert row["marks"] == {"AAA": 101.0} and row["value"] == 0.5 + 5 * 101.0 + 10.0 * 501.0
    assert row["idle_value"] == 10.0 * 501.0 and row["stock_value"] == 505.0


def test_h1_h1_check_어느_쪽을_먼저_읽어도_된다():
    for first in ("h1", "h1_check"):
        r = subprocess.run([sys.executable, "-I", "-c",
                            f"import sys; sys.path.insert(0, {str(ROOT)!r}); import {first}; import h1, h1_check; "
                            "print(h1_check.EPS_CASH, h1.rule_constants('us')['eps_rel'])"],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0 and r.stdout.split() == ["1e-06", "1e-09"], r.stderr
