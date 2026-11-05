"""H1 단계 5 — 재현 h1_replay.py 시험 (설계 docs/h1-forward-design.md §5). 인터넷·claude 없음.

- 비교 함수(M1~M7·M10·K)를 손으로 만든 입력으로: 받아들이는 차이(K1·K2·K8·K11·K12)는 통과, 그 밖의 차이는 실패.
  NaN·inf 는 늘 차이(검토 5 P-4). 팀 합계·K5·지수 B&H 마지막 날·두 번째 실행 확인도 '틀린 입력이면 실패'를 직접 본다(검토 5 P-9).
- K9 세율 표: R2 표의 기존 줄은 그대로·덧붙인 줄은 모든 재현 창 뒤 → 통과(⑥-ii 줄 추가가 재현을 막지 않음), 기존 줄을 바꾸거나
  창 안에 줄을 더하면 실패(검토 5 P-1).
- 하네스 모듈 경로 확인: 가짜 R2 폴더에서 저장소 모듈을 읽게 하면 종료 코드 3 → 환경 문제(통과도 기록도 없음).
  R2 커밋이 고정값(R2_COMMIT)이 아니면 환경 문제(검토 5 P-5).
- W3 합성 차등 재현 전체(빠름): 기준값(R2 sim_team, python -I) == 새 코드(h1.start·run), 보유 상태(M10)까지 같고, 장면 s1~s7 이
  실제로 그 길을 지남. 장면 확인은 전제가 빠지면 실패(검토 5 P-3). 일부러 규칙을 바꾼 새 코드(쓸어 담기 문턱 1 → 0.5)와
  '정지 중 판단 쉼'을 지우고 L15 보유일수 확인도 끈 사본(검토 5 P-2)은 W3 가 잡는다.
- 실데이터 W1 을 몇 봉으로 줄여 한 번(기준값·실행기 전체가 같은 숫자).
- 실행 갈래(가짜 h1.start·run): 같은 날 두 번째 실행이 파일을 바꾸거나 실패하면 잡고, h1.run 안의 Ctrl-C(130)는 재현 전체를 멈춤(P-7).
- 기록 갈래: 통과(모든 창)면 보고서를 먼저 쓰고 → replay_pass.json 한 줄(started_at·passed_at·기준값 sha256) → 보고서에 '기록함',
  관문이 그 줄로 열림(P-8). 실패·일부 창(3)·코드가 바뀜·골든 깨짐이면 기록 없음.
R2 브랜치(origin/research-r2-2026-11-04)가 없으면 그 시험만 건너뜀(git fetch 필요).
"""
import contextlib
import copy
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyst          # noqa: E402
import h1               # noqa: E402
import h1_check         # noqa: E402
import h1_replay as RP  # noqa: E402

TR = h1.TRAINERS


def _boom(*a, **k):
    raise AssertionError("시험이 진짜 claude 를 부르려 했어요")


@pytest.fixture(autouse=True)
def guards(monkeypatch):
    import h1_repo_guard as rg
    before = rg.snapshot(ROOT)
    monkeypatch.setattr(analyst, "analyze_logged", _boom)
    monkeypatch.setattr(analyst, "analyze", _boom)
    monkeypatch.setattr(analyst, "claude_cli_version", _boom)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("인터넷")))
    real_run = subprocess.run

    def guarded(args, *a, **k):
        if isinstance(args, (list, tuple)) and args and str(args[0]).endswith("claude"):
            raise AssertionError("시험이 claude 프로세스를 띄우려 했어요")
        return real_run(args, *a, **k)
    monkeypatch.setattr(subprocess, "run", guarded)
    yield
    moved = rg.changes(before, rg.snapshot(ROOT))
    assert not moved, "시험이 저장소 state/·results/ 를 건드렸어요: " + "; ".join(moved[:5])


def _r2_available():
    p = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "-q", RP.R2_REF], capture_output=True)
    return p.returncode == 0


needs_r2 = pytest.mark.skipif(not _r2_available(), reason="R2 브랜치 없음(git fetch origin research-r2-2026-11-04)")


# ============================ 비교 함수: 손으로 만든 입력 ============================

D = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
LAST = D[-1]


def _day(d, value=100.0, cash=1e-8, stock=0.0, idle=100.0, units=1.0, events=(), over=0):
    return {"date": d, "value": value, "cash": cash, "stock_value": stock, "idle_value": idle, "idle_units": units,
            "events": list(events), "over_slots": over}


def _states():
    """세 트레이너가 똑같은 아주 작은 장부(A0·A1)."""
    out = {}
    for arm in h1.ARMS:
        out[arm] = {}
        for tn in TR:
            out[arm][tn] = {
                "fills": [{"date": D[1], "kind": "idle", "code": "SPY", "side": "buy", "qty": 1.25, "price": 80.0,
                           "cash_delta": -100.0},
                          {"date": D[2], "kind": "stock", "code": "AAA", "side": "buy", "qty": 3, "price": 10.0,
                           "cash_delta": -30.03}],
                "skips": [{"date": D[2], "code": "BBB", "kind": "현금부족"}],
                "orders": [{"signal_date": D[1], "code": "AAA", "action": "매수", "reason": "가짜 매수"}],
                "days": [_day(d) for d in D],
            }
    return out


def _held(i):
    """i 번째 날 종가 뒤 보유 상태: AAA 를 D[2] 에 3주 10.0 에 사서 들고 있음(보유일수 = 산 뒤 지난 봉 수)."""
    return {"AAA": [3, 10.0, i - 2, D[2]]} if i >= 2 else {}


def _base():
    """하네스 결과 모양(그 창 하나)."""
    arms = {}
    for arm in h1.ARMS:
        none = {"fills": [], "skips": [], "orders": [], "events": [], "daily": [], "over_slots": {}}
        for tn in TR:
            none["fills"] += [{"sleeve": tn, "date": D[1], "kind": "index", "code": "SPY", "side": "매수", "qty": 1.25,
                               "price": 80.0, "cash": -100.0},
                              {"sleeve": tn, "date": D[2], "kind": "stock", "code": "AAA", "side": "매수", "qty": 3,
                               "price": 10.0, "cash": -30.03}]
            none["skips"].append({"sleeve": tn, "date": D[2], "code": "BBB", "kind": "현금부족"})
            none["orders"].append({"sleeve": tn, "signal_date": D[1], "code": "AAA", "action": "매수",
                                   "reason": "가짜 매수"})
            none["over_slots"][tn] = 0
        for d in D:
            row = {"date": d, "value": 300.0, "stock": 0.0, "index": 300.0, "cash": 3e-8}
            for tn in TR:
                row.update({f"v_{tn}": 100.0, f"stock_{tn}": 0.0, f"index_{tn}": 100.0, f"cash_{tn}": 1e-8,
                            f"units_{tn}": 1.0})
            none["daily"].append(row)
        none["positions"] = [{"date": d, "sleeves": {tn: _held(i) for tn in TR}} for i, d in enumerate(D)]
        arms[arm] = {"none": none, "current": {"events": []}}
    return {"i1": LAST, "dates": list(D), "arms": arms}


def _h_pos():
    """새 코드 쪽 보유 상태(run_h1_window 가 날마다 장부 파일에서 읽는 모양)."""
    return {d: {arm: {tn: _held(i) for tn in TR} for arm in h1.ARMS} for i, d in enumerate(D)}


def test_같은_입력이면_M1_M5_M10_모두_통과():
    out = RP.compare_window("us", _states(), _base(), do_m6=False, do_m7=False, h_pos=_h_pos())
    assert all(out[m]["ok"] for m in ("M1", "M2", "M3", "M4", "M5", "M10")), out
    assert out["M10"]["n"] == 2 * 2 * 3                                          # 보유한 날 2 × 장부 2 × 트레이너 3


@pytest.mark.parametrize("field,delta,ok", [
    ("idle_qty", 1e-12, True),      # K12: 지수 수량 상대 차 ≤ 1e-9
    ("idle_qty", 1e-6, False),
    ("stock_qty", 1, False),         # 주식 수량은 정확히
    ("price", 1e-13, False),         # 체결가는 정확히 같아야(1ulp 도 차이)
    ("cash", 1e-8, True),            # 현금 변화 절대 차 ≤ 1e-6
    ("cash", 1e-3, False),
])
def test_M1_체결_허용_오차(field, delta, ok):
    st = _states()
    f_idle, f_stock = st["A1"][TR[0]]["fills"]
    if field == "idle_qty":
        f_idle["qty"] = f_idle["qty"] * (1 + delta)
    elif field == "stock_qty":
        f_stock["qty"] += delta
    elif field == "price":
        f_stock["price"] = f_stock["price"] + delta
    else:
        f_stock["cash_delta"] += delta
    assert RP.compare_fills(st, "A1", _base()["arms"]["A1"]["none"], LAST)["ok"] is ok


def test_M1_빠지거나_더한_체결은_실패():
    st = _states()
    st["A0"][TR[1]]["fills"].pop()
    assert not RP.compare_fills(st, "A0", _base()["arms"]["A0"]["none"], LAST)["ok"]
    st = _states()
    st["A0"][TR[1]]["fills"].append({"date": LAST, "kind": "stock", "code": "CCC", "side": "sell", "qty": 1,
                                     "price": 5.0, "cash_delta": 4.9})
    out = RP.compare_fills(st, "A0", _base()["arms"]["A0"]["none"], LAST)
    assert not out["ok"], "마지막 봉의 체결은 K1 대상이 아님(체결은 마지막 봉도 비교)"


def test_M2_보류_차이와_재현에서_팀장_보류는_차이():
    st = _states()
    st["A1"][TR[2]]["skips"][0]["kind"] = "0주"
    assert not RP.compare_skips(st, "A1", _base()["arms"]["A1"]["none"], LAST)["ok"]
    st = _states()
    st["A1"][TR[2]]["skips"].append({"date": D[2], "code": "CCC", "kind": "팀장hold"})   # 재현은 팀장 끔 → 있으면 안 됨
    assert not RP.compare_skips(st, "A1", _base()["arms"]["A1"]["none"], LAST)["ok"]


def test_M3_K1_마지막_봉_주문은_빼고_그_전은_비교():
    b = _base()["arms"]["A0"]["none"]
    st = _states()
    st["A0"][TR[0]]["orders"].append({"signal_date": LAST, "code": "ZZZ", "action": "매수", "reason": "마지막 봉"})
    out = RP.compare_orders(st, "A0", b, LAST)
    assert out["ok"] and out["k1_excluded"] == 1
    st["A0"][TR[0]]["orders"].append({"signal_date": D[2], "code": "ZZZ", "action": "매수", "reason": "그 전 봉"})
    assert not RP.compare_orders(st, "A0", b, LAST)["ok"]
    st = _states()
    st["A0"][TR[0]]["orders"][0]["reason"] = "사유 글이 다름"                 # 사유 글도 비교(14자 자르지 않음)
    assert not RP.compare_orders(st, "A0", b, LAST)["ok"]


def test_K11_빈자리_부족은_마지막_봉을_빼고_합계만():
    b = _base()["arms"]["A1"]["none"]
    st = _states()
    st["A1"][TR[1]]["days"][-1]["over_slots"] = 4                               # 마지막 봉 → 뺌
    assert RP.compare_over_slots(st, "A1", b, LAST)["ok"]
    st["A1"][TR[1]]["days"][1]["over_slots"] = 1
    assert not RP.compare_over_slots(st, "A1", b, LAST)["ok"]
    b["over_slots"][TR[1]] = 1
    assert RP.compare_over_slots(st, "A1", b, LAST)["ok"]


@pytest.mark.parametrize("key,delta,ok", [
    ("value", 1e-12, True), ("value", 1e-6, False), ("idle_units", 1e-12, True), ("idle_units", 1e-5, False),
    ("cash", 1e-8, True),           # 현금은 절대 차: 1e-8 vs 2e-8 은 상대로는 50% 지만 받아들임(probe4)
    ("cash", 1e-3, False),
])
def test_M4_매일_값_허용_오차(key, delta, ok):
    st = _states()
    row = st["A1"][TR[0]]["days"][2]
    row[key] = row[key] * (1 + delta) if key != "cash" else row[key] + delta
    assert RP.compare_daily(st, "A1", _base()["arms"]["A1"]["none"], LAST)["ok"] is ok


def test_M4_빠진_날은_실패():
    st = _states()
    st["A0"][TR[2]]["days"].pop(1)
    assert not RP.compare_daily(st, "A0", _base()["arms"]["A0"]["none"], LAST)["ok"]


@pytest.mark.parametrize("key,delta", [("value", 1e-6), ("stock", 1.0), ("index", 1e-6), ("cash", 1e-3)])
def test_M4_팀_합계가_다르면_실패(key, delta):
    """검토 5 P-9(T1): 트레이너별 값은 같고 R2 팀 합계만 다르면 — 팀 합계 비교가 꺼져 있으면 통과해 버린다."""
    b = _base()["arms"]["A0"]["none"]
    b["daily"][2][key] += delta if key in ("stock", "cash") else b["daily"][2][key] * delta
    out = RP.compare_daily(_states(), "A0", b, LAST)
    assert not out["ok"] and any("팀" in d for d in out["diffs"]), out["diffs"]


def test_K12_NaN_inf_는_늘_차이():
    """검토 5 P-4: 두 쪽이 똑같이 NaN 이어도, inf 끼리여도 '같음'이 아니다(상대 차·현금 차가 무한대)."""
    assert RP._rel(math.nan, math.nan) == math.inf and RP._rel(math.inf, math.inf) == math.inf
    assert RP._rel(1.0, math.nan) == math.inf and RP._abs(math.nan, 0.0) == math.inf
    assert RP._abs(-math.inf, -math.inf) == math.inf and RP._rel(2.0, 2.0) == 0.0
    for key, rk in (("value", "v_"), ("idle_units", "units_"), ("cash", "cash_")):
        st, b = _states(), _base()
        st["A1"][TR[0]]["days"][2][key] = math.nan
        assert not RP.compare_daily(st, "A1", b["arms"]["A1"]["none"], LAST)["ok"], key
        b["arms"]["A1"]["none"]["daily"][2][rk + TR[0]] = math.nan                # 두 쪽 다 NaN
        assert not RP.compare_daily(st, "A1", b["arms"]["A1"]["none"], LAST)["ok"], key
    st, b = _states(), _base()
    st["A1"][TR[0]]["fills"][1]["cash_delta"] = math.nan
    b["arms"]["A1"]["none"]["fills"][1]["cash"] = math.nan
    assert not RP.compare_fills(st, "A1", b["arms"]["A1"]["none"], LAST)["ok"]
    st, b = _states(), _base()
    st["A1"][TR[0]]["fills"][0]["qty"] = math.inf
    b["arms"]["A1"]["none"]["fills"][0]["qty"] = math.inf
    assert not RP.compare_fills(st, "A1", b["arms"]["A1"]["none"], LAST)["ok"]


@pytest.mark.parametrize("i,value", [
    (0, 4),                           # 주식 수
    (1, math.nextafter(10.0, 11.0)),  # 매수가(1ulp 도 차이)
    (2, 2),                           # 보유일수(정지일을 셌다 등)
    (3, D[1]),                        # 매수일
    (1, math.nan),                    # NaN 은 늘 차이
])
def test_M10_보유_상태는_정확히_같아야(i, value):
    h = _h_pos()
    h[D[3]]["A1"][TR[1]]["AAA"][i] = value
    out = RP.compare_positions(h, _base(), D)
    assert not out["ok"] and len(out["diffs"]) == 1 and RP.POS_FIELDS[i] in out["diffs"][0], out["diffs"]


def test_M10_보유_종목이_다르거나_날이_빠지면_실패():
    h = _h_pos()
    h[D[2]]["A0"][TR[0]]["BBB"] = [1, 5.0, 0, D[2]]
    assert not RP.compare_positions(h, _base(), D)["ok"]
    h = _h_pos()
    del h[D[1]]
    out = RP.compare_positions(h, _base(), D)
    assert not out["ok"] and "기록 없음" in out["diffs"][0]
    b = _base()
    b["arms"]["A1"]["none"]["positions"].pop()                                   # 기준값 쪽이 빠져도
    assert not RP.compare_positions(_h_pos(), b, D)["ok"]


def test_M5_그림자_서킷_첫_발동일과_K1():
    ev = {"kind": "shadow_breaker", "why": "하루", "first": True}
    st = _states()
    st["A1"][TR[0]]["days"][-1]["events"] = [ev]                                # 마지막 봉만 → K1 로 뺌
    cur = {"events": []}
    assert RP.compare_shadow(st, "A1", cur, LAST)["ok"]
    st["A1"][TR[0]]["days"][2]["events"] = [ev]
    assert not RP.compare_shadow(st, "A1", cur, LAST)["ok"]
    cur = {"events": [{"kind": "서킷(지금)", "sleeve": TR[0], "date": D[2]}]}
    assert RP.compare_shadow(st, "A1", cur, LAST)["ok"]
    cur = {"events": [{"kind": "서킷(지금)", "sleeve": TR[0], "date": D[1]}]}   # 날짜가 다르면 실패
    assert not RP.compare_shadow(st, "A1", cur, LAST)["ok"]


def _bh_states(opens, closes, total=100_000.0):
    st = {"A0": {}, "A1": {}}
    for arm in h1.ARMS:
        for tn in TR:
            st[arm][tn] = {"start_cash": total / 3, "wallet": {"fee_rate": 0.001, "slippage": 0.0005},
                           "days": [{"date": d, "idle_open": o, "idle_close": c} for d, o, c in zip(D, opens, closes)]}
    return st


def test_M6_지수_BH_K2_마지막_날은_단위_곱하기_종가():
    opens, closes = [100.0, 101.0, 102.0, 103.0], [100.5, 101.5, 102.5, 103.5]
    st = _bh_states(opens, closes)
    total = sum(st["A1"][tn]["start_cash"] for tn in TR)
    units = total / (opens[1] * (1 + 0.0005) * (1 + 0.001))
    eq = [units * c for c in closes[1:]]
    sold = closes[-1] * (1 - 0.0005) * units
    eq[-1] = sold - sold * 0.001                                                 # R2 는 마지막 날 매도 비용을 뺌(K2)
    base = {"bh": {"units": units, "equity": eq, "dates": D[1:], "last_close": closes[-1]}}
    assert RP.compare_bh("us", st, base)["ok"]
    bad = copy.deepcopy(base)
    bad["bh"]["units"] = units * (1 + 1e-15)
    assert not RP.compare_bh("us", st, bad)["ok"]                                # 단위는 비트까지
    bad = copy.deepcopy(base)
    bad["bh"]["last_close"] = closes[-1] * 1.01                                  # 검토 5 P-9(T10): 마지막 날만 다름
    out = RP.compare_bh("us", st, bad)
    assert not out["ok"] and out["diffs"] == ["마지막 날 단위 × 종가가 다름"]


def test_M7_이자_금리가_다르면_실패():
    import pandas as pd
    st = {"A0": {tn: {"days": [{"date": d, "value": 100.0, "cash": 50.0, "stock_value": 50.0, "idle_value": 0.0,
                                "idle_units": 0.0, "prev_cal_date": prev}
                               for d, prev in zip(D, ["2026-01-02"] + D[:-1])]} for tn in TR}}
    series = pd.Series([4.0, 4.1, 4.2, 4.3, 4.4], index=pd.DatetimeIndex(["2026-01-02"] + D))
    base = {"rates": {"dates": list(D), "values": [4.0, 4.1, 4.2, 4.3]}}       # 전 거래일 값(prev_day)
    assert RP.compare_interest("us", st, base, series)["ok"]
    base["rates"]["values"][2] = 9.9
    assert not RP.compare_interest("us", st, base, series)["ok"]


R2_TAX = [list(x) for x in h1.KR_SELL_TAX]          # 지금 H1 표 == R2 표(재현 K9 가 매번 확인)


def _k_inputs():
    import pandas as pd
    idx = pd.bdate_range("2025-06-02", "2026-01-08")
    full = pd.DataFrame({"Open": 1.0, "Close": 1.0}, index=idx)
    base = {"dates": list(D), "_kr_sell_tax": copy.deepcopy(R2_TAX), "_kr_universe": None, "_kind": "synthetic"}
    return full, base


def test_K_전제_확인_70봉_새상장_세율_종목군():
    import pandas as pd
    full, base = _k_inputs()
    assert RP.k_checks("kr", {"111111": full}, ["111111"], base, D[0], LAST)["ok"]
    young = full[full.index >= pd.Timestamp("2025-11-01")]                      # 창 시작 전 50봉 남짓
    assert not RP.k_checks("kr", {"111111": young}, ["111111"], base, D[0], LAST)["ok"]
    new = full[full.index >= pd.Timestamp(D[1])]                               # 창 안에서 새로 상장
    assert not RP.k_checks("kr", {"111111": full, "222222": new}, ["111111", "222222"], base, D[0], LAST)["ok"]
    bad = dict(base, _kr_sell_tax=[["0000-01-01", 0.003]])
    assert not RP.k_checks("kr", {"111111": full}, ["111111"], bad, D[0], LAST)["ok"]
    uni = dict(base, _kr_universe=["005930"], _kind="real")
    assert not RP.k_checks("kr", {"111111": full}, ["111111"], uni, D[0], LAST)["ok"]


def test_K5_종목군_어디에도_봉이_없는_날은_실패():
    """검토 5 P-9(T2): 창 날짜 중 종목군 어느 종목에도 확정 봉이 없는 날(오래된 봉 기준이 갈릴 수 있음)."""
    full, base = _k_inputs()
    gap = full.drop(full.index[full.index == "2026-01-07"])
    out = RP.k_checks("kr", {"111111": gap}, ["111111"], base, D[0], LAST)
    assert not out["ok"] and any(d.startswith("K5") and "2026-01-07" in d for d in out["diffs"]), out["diffs"]


@pytest.mark.parametrize("h_table,ok", [
    (R2_TAX, True),
    (R2_TAX + [["2027-01-01", 0.0015]], True),                                   # 검토 5 P-1 시나리오(⑥-ii 줄 추가)
    (R2_TAX + [["2027-01-01", 0.0015], ["2028-01-01", 0.001]], True),
    (R2_TAX[:-1] + [[R2_TAX[-1][0], 0.0019]], False),                            # 기존 줄의 세율을 바꿈
    (R2_TAX[:1] + [["2019-06-04", 0.0025]] + R2_TAX[2:], False),                 # 기존 줄의 시행일을 바꿈
    (R2_TAX[:-1], False),                                                        # 기존 줄을 지움
    (R2_TAX + [["2026-10-01", 0.0015]], False),                                  # 더한 줄이 재현 창(W1 끝 2026-11-03) 안
    (R2_TAX + [[RP.replay_last_day(), 0.0015]], False),                          # 마지막 봉 당일도 창 안
    (R2_TAX + [["2028-01-01", 0.001], ["2027-01-01", 0.0015]], False),           # 날짜 순서가 거꾸로
])
def test_K9_세율_표_기존_줄은_같고_더한_줄은_재현_창_뒤(h_table, ok):
    probs = RP.tax_table_problems(h_table, R2_TAX, RP.replay_last_day())
    assert (probs == []) is ok, probs
    assert RP.replay_last_day() == "2026-11-03"


def test_K9_k_checks_는_지금_h1_세율_표를_본다(monkeypatch):
    full, base = _k_inputs()
    monkeypatch.setattr(h1, "KR_SELL_TAX", h1.KR_SELL_TAX + (("2027-01-01", 0.0015),))
    assert RP.k_checks("kr", {"111111": full}, ["111111"], base, D[0], LAST)["ok"]
    monkeypatch.setattr(h1, "KR_SELL_TAX", h1.KR_SELL_TAX[:-1] + (("2026-01-01", 0.0019),))
    out = RP.k_checks("kr", {"111111": full}, ["111111"], base, D[0], LAST)
    assert not out["ok"] and "K9" in out["diffs"][0]
    monkeypatch.setattr(h1, "KR_SELL_TAX", tuple(tuple(x) for x in R2_TAX) + (("2026-06-15", 0.0015),))
    assert not RP.k_checks("kr", {"111111": full}, ["111111"], base, D[0], LAST)["ok"]


def _runs_file(root, lines):
    root.mkdir(parents=True, exist_ok=True)
    (root / "runs.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines), encoding="utf-8")


def test_M8_실행_일지_D_와_허용_밖_경고(tmp_path):
    root = tmp_path / "h1"
    lines = [{"event": "end", "market": "kr", "exit_code": 0,
              "problems": [{"level": "W", "code": "W2"}, {"level": "W", "code": "W3"}]},
             {"event": "end", "market": "kr", "exit_code": 0, "problems": [{"level": "W", "code": "W5"}]},
             {"event": "end", "market": "kr", "exit_code": 4, "problems": [{"level": "D", "code": "D3"}]},
             {"event": "end", "market": "us", "exit_code": 0, "problems": [{"level": "W", "code": "W1"}]}]
    _runs_file(root, lines)
    r = RP.check_runs(root, "kr")
    assert r["w_other"] == ["W5"] and r["d"] == {"D3": 1} and r["bad_exit"] == {4: 1} and r["n_runs"] == 3


def test_M8_W4_는_W2_창의_네_종목만_허용(tmp_path):
    """검토 5 P-11: W4(종목군 시세 못 받음)는 W2 창에서 아직 상장 전인 316140·329180·402340·373220 만. W1·W3 창에선 허용 밖."""
    def w4(c):
        return {"level": "W", "code": "W4", "detail": f"종목군 {c} 시세 못 받음 → 건너뜀"}
    root = tmp_path / "a"
    _runs_file(root, [{"event": "end", "market": "kr", "exit_code": 0, "problems": [w4("316140"), w4("373220")]}])
    assert RP.check_runs(root, "kr", RP.WINDOWS["W2-kr"]["w4_ok"])["w_other"] == []
    assert RP.check_runs(root, "kr")["w_other"] == ["W4(316140, 373220)"]          # 다른 창(허용 종목 없음)
    root = tmp_path / "b"
    _runs_file(root, [{"event": "end", "market": "kr", "exit_code": 0, "problems": [w4("005930"), w4("402340")]}])
    r = RP.check_runs(root, "kr", RP.W4_ALLOWED_W2)
    assert r["w_other"] == ["W4(005930)"] and r["w4_codes"] == {"005930": 1, "402340": 1}
    assert RP.W4_ALLOWED_W2 == ("316140", "329180", "402340", "373220")
    assert [n for n, s in RP.WINDOWS.items() if s.get("w4_ok")] == ["W2-kr"]


# ============================ 하네스 · R2 풀기 · 커밋 고정 ============================

def test_R2_가_없으면_환경_문제와_fetch_안내(tmp_path):
    with pytest.raises(RP.ReplayEnvError, match="git fetch origin research-r2-2026-11-04"):
        RP.extract_r2("refs/없는/가지-12345", tmp_path / "r2")
    with pytest.raises(RP.ReplayEnvError, match="git fetch origin research-r2-2026-11-04"):
        RP.check_r2_commit("refs/없는/가지-12345")


@needs_r2
def test_R2_커밋은_고정값이어야(tmp_path):
    """검토 5 P-5: 연구 브랜치 이름이 다른 커밋을 가리키면(실수 커밋·강제 푸시) 풀기 전에 환경 문제(4)."""
    assert RP.check_r2_commit(RP.R2_REF) == RP.R2_COMMIT == "22b7934c4b183d38bf411d132ddec5e5d7742195"
    with pytest.raises(RP.ReplayEnvError, match="고정"):
        RP.check_r2_commit("HEAD")
    with pytest.raises(RP.ReplayEnvError, match="고정"):
        RP.replay(["W3"], "HEAD", tmp_path / "w", progress=lambda *a: None)
    assert not (tmp_path / "w" / "r2").exists()


def test_하네스는_모듈이_임시_폴더_밖에서_읽히면_멈춤(tmp_path):
    """가짜 R2 폴더: sim_team.py 가 지금 저장소를 sys.path 맨 앞에 넣으면 main·team 등이 저장소에서 읽힌다 → 종료 코드 3."""
    fake = tmp_path / "fake_r2"
    rep = fake / RP.R2_DIR
    rep.mkdir(parents=True)
    (rep / "sim_team.py").write_text(f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n", encoding="utf-8")
    with pytest.raises(RP.ReplayEnvError, match="R2 임시 폴더 밖"):
        RP.run_harness(rep, [], tmp_path / "work")


# ============================ 실행 갈래 (가짜 h1.start·run) ============================

SPEC = {"group": "W1", "market": "kr", "start": D[0], "end": D[-1], "kind": "real"}


class _Src:
    """run_h1_window 이 쓰는 만큼만 있는 가짜 시세(날짜 목록·시계·가짜 FinanceDataReader 자리)."""
    mk = "kr"

    def __init__(self):
        self.clock = None

    def dates(self, a, b):
        return [d for d in D if a <= d <= b]

    def fdr_installed(self):
        return contextlib.nullcontext()


def _fake_runs(monkeypatch, root, *, first=None, second=None, touch=False, on_fail=None):
    """h1.start·h1.run 을 가짜로. 날마다 첫 실행은 장부 파일 하나를 그날 글자로 쓰고 first(날) 를, 같은 날 두 번째 실행은
    second(날) 를 돌려준다(기본 0). touch 면 두 번째 실행이 장부 파일을 바꾼다. on_fail(root, 날, 코드) 은 0 이 아닐 때."""
    seen = []
    led = Path(root) / "kr" / "ledger.json"

    def call(mk, root=None, source=None, **k):
        day = source.clock.date().isoformat()
        again = bool(seen) and seen[-1] == day
        seen.append(day)
        led.parent.mkdir(parents=True, exist_ok=True)
        if not again:
            led.write_text(day, encoding="utf-8")
            code = (first or (lambda d: 0))(day)
        else:
            if touch:
                led.write_text(day + " 두 번째", encoding="utf-8")
            code = (second or (lambda d: 0))(day)
        if code and on_fail:
            on_fail(Path(root), day, code)
        return code
    monkeypatch.setattr(h1, "start", call)
    monkeypatch.setattr(h1, "run", call)
    monkeypatch.setattr(RP, "positions_now", lambda root, market: {"A0": {}, "A1": {}})
    return seen


def test_M9_두_번째_실행이_파일을_바꾸면_같지_않음(tmp_path, monkeypatch):
    """검토 5 P-9(T19): 같은 날 두 번째 실행 전·후 파일 sha256 을 실제로 비교한다."""
    _fake_runs(monkeypatch, tmp_path / "a")
    rr = RP.run_h1_window("T", SPEC, _Src(), tmp_path / "a", tmp_path / "a.log", progress=None)
    assert len(rr["twice"]) == len(D) and all(x["same"] for x in rr["twice"]) and not RP.run_problems(rr)
    assert sorted(rr["positions"]) == D                                          # 날마다 보유 상태를 적음(M10)
    _fake_runs(monkeypatch, tmp_path / "b", touch=True)
    rr = RP.run_h1_window("T", SPEC, _Src(), tmp_path / "b", tmp_path / "b.log", progress=None)
    assert len(rr["twice"]) == len(D) and not any(x["same"] for x in rr["twice"])


def test_같은_날_두_번째_실행이_실패하면_창이_멈추고_원인이_보고서에(tmp_path, monkeypatch):
    """검토 5 P-7·P-8·P-9(T22): 첫 실행 0 이어도 두 번째 실행이 0 이 아니면 멈추고, 결과·보고서에 '두 번째 run' 과 L 코드가 남는다."""
    assert RP.run_problems({"exit_codes": [{"code": 0, "code2": 2}]})
    assert not RP.run_problems({"exit_codes": [{"code": 0, "code2": None}, {"code": 0, "code2": 0}]})

    def fail(root, day, code):
        h1._append_log(root, "errors.jsonl", {"market": "kr", "date": day, "run_id": "r-가짜", "problems": [
            {"code": "L15", "arm": "A1", "trainer": TR[1], "date": day, "detail": "AAA 보유일수 3 ≠ 정지 아닌 처리 봉 수 2"}]})
        h1._append_log(root, "runs.jsonl", {"event": "end", "market": "kr", "exit_code": code, "message": "장부 점검 실패",
                                            "problems": [{"level": "L", "code": "L15", "date": day, "detail": "보유일수"}]})
    ch = h1.code_hash()[0]
    work = tmp_path / "w"
    _fake_runs(monkeypatch, work / "root-W2-kr" / "h1", second=lambda d: 2 if d == D[1] else 0, on_fail=fail)
    out = RP.replay_window("W2-kr", RP.WINDOWS["W2-kr"] | {"start": D[0], "end": D[-1]}, None, _Src(), work, ch,
                           h1.env_info(), progress=lambda *a: None)
    assert out["stopped"]["detail"] == f"실행이 멈춤: {D[1]} 같은 날 두 번째 run 종료 코드 2(첫 실행은 0)"
    assert out["exit_codes"] == {0: 2} and out["exit_codes2"] == {0: 1, 2: 1}
    assert all(not out["checks"][m]["ok"] for m in RP.CHECK_ORDER)
    cause = "\n".join(out["stopped"]["cause"])
    assert "L15" in cause and "보유일수 3" in cause and "종료 코드 2" in cause
    res = _fake_result(passed=False)
    res["windows"]["W2-kr"] = dict(out, ok=False, ref={})
    lines = []
    assert RP.finish(res, tmp_path / "h1", progress=lines.append) == RP.EXIT_DIFF
    rep = next((tmp_path / "h1" / "reports").glob("replay-*.md")).read_text(encoding="utf-8")
    assert "같은 날 두 번째 run 종료 코드 2" in rep and "L15" in rep and "보유일수 3" in rep
    assert any("두 번째 run" in x for x in lines) and any("L15" in x for x in lines)
    assert not (tmp_path / "h1" / "replay_pass.json").exists()


def test_h1_run_안에서_Ctrl_C_면_재현_전체가_멈춤(tmp_path, monkeypatch):
    """검토 5 P-7: h1.run 은 Ctrl-C 를 잡아 130 을 돌려준다 → 재현은 그 창만 건너뛰지 않고 전체를 멈춘다(KeyboardInterrupt)."""
    _fake_runs(monkeypatch, tmp_path / "a", first=lambda d: h1.EXIT_INTERRUPT if d == D[2] else 0)
    with pytest.raises(KeyboardInterrupt):
        RP.run_h1_window("T", SPEC, _Src(), tmp_path / "a", tmp_path / "a.log", progress=None)
    _fake_runs(monkeypatch, tmp_path / "b", second=lambda d: h1.EXIT_INTERRUPT)
    with pytest.raises(KeyboardInterrupt):
        RP.run_h1_window("T", SPEC, _Src(), tmp_path / "b", tmp_path / "b.log", progress=None)
    monkeypatch.setattr(RP, "replay", lambda *a, **k: RP.run_h1_window("T", SPEC, _Src(), tmp_path / "c",
                                                                       tmp_path / "c.log", progress=None))
    _fake_runs(monkeypatch, tmp_path / "c", first=lambda d: h1.EXIT_INTERRUPT)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    assert RP.cli(["--root", str(tmp_path / "h1"), "--windows", "W3"]) == RP.EXIT_INTERRUPT
    assert not (tmp_path / "h1" / "replay_pass.json").exists()


def test_진행_표시는_25봉마다_화면으로(tmp_path, monkeypatch, capsys):
    """검토 5 P-6: h1 의 실행 요약은 로그 파일로, 재현 진행 표시는 화면(sys.stdout)으로."""
    import pandas as pd
    days = [d.date().isoformat() for d in pd.bdate_range("2026-01-05", periods=26)]
    monkeypatch.setattr(_Src, "dates", lambda self, a, b: days)
    _fake_runs(monkeypatch, tmp_path / "h1")
    print_in_run = h1.run

    def chatty(*a, **k):
        print("h1 실행 요약 한 줄")
        return print_in_run(*a, **k)
    monkeypatch.setattr(h1, "run", chatty)
    rr = RP.run_h1_window("T", SPEC | {"end": days[-1]}, _Src(), tmp_path / "h1", tmp_path / "h1.log", twice=False,
                          progress=RP._say)
    out = capsys.readouterr().out
    log = (tmp_path / "h1.log").read_text(encoding="utf-8")
    assert len(rr["exit_codes"]) == 26
    assert "T: 25/26봉" in out and "h1 실행 요약" not in out
    assert "h1 실행 요약" in log and "25/26봉" not in log


# ============================ W3 합성 차등 재현 (전체) ============================

def test_W3_합성_세계는_결정적이고_값이_비트까지_보존(tmp_path):
    m1 = RP.make_w3(tmp_path / "a")
    m2 = RP.make_w3(tmp_path / "b")
    for f in sorted((tmp_path / "a").iterdir()):
        assert f.read_bytes() == (tmp_path / "b" / f.name).read_bytes(), f.name
    assert m1["s5"] == m2["s5"]
    assert 0.98 < m1["s5"]["left1"] < 0.995 and 0.0 < m1["s5"]["left2"] < 0.02
    assert m1["W"][29] == "2019-05-31" and m1["W"][30] == "2019-06-03"          # 세율 경계 전날·당일
    assert m1["codes"]["Z"] == "003550" and m1["plan"]["스프린터"]["sell_after"] == [["207940", 31]]


@pytest.fixture(scope="module")
def w3_result(tmp_path_factory):
    if not _r2_available():
        pytest.skip("R2 브랜치 없음")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(analyst, "analyze_logged", _boom)
        mp.setattr(analyst, "claude_cli_version", _boom)
        work = tmp_path_factory.mktemp("w3")
        res = RP.replay(["W3"], RP.R2_REF, work / "w", progress=lambda *a: None)
    return res, work


@needs_r2
def test_W3_전체_기준값과_같고_장면이_모두_그_길을_지남(w3_result):
    res, _ = w3_result
    w = res["windows"]["W3-kr"]
    assert w["ok"], {m: c["detail"] for m, c in w["checks"].items() if not c["ok"]}
    for m in RP.REQUIRED["W3"]:
        assert w["checks"][m]["ok"], (m, w["checks"][m])
    assert set(w["scenes"]) == {"s1", "s2", "s3", "s4", "s5", "s6", "s7"}
    assert all(v["ok"] for v in w["scenes"].values()), w["scenes"]
    assert w["checks"]["M1"]["arms"]["A1"]["n_h1"] > 20 and w["checks"]["M2"]["arms"]["A1"]["n_h1"] >= 1
    assert w["checks"]["M10"]["n"] > 300                                         # 보유 상태를 실제로 비교함(검토 5 P-2)
    assert set(w["warnings"]) <= {"W2", "W3"} and w["warnings"].get("W2")
    assert not res["complete"] and res["passed"]                                 # 일부 창 → 기록 대상 아님
    assert res["r2_commit"] == RP.R2_COMMIT and len(res["baseline_sha256"]) == 64
    assert RP._sha_file(res["baseline_file"]) == res["baseline_sha256"]


def _w3_states(res):
    return h1.load_market("kr", res["windows"]["W3-kr"]["root"], repair=False).states


def _fills(st, arm, tn):
    return st[arm][tn]["fills"]


def _row(st, arm, tn, d):
    return next(r for r in st[arm][tn]["days"] if r["date"] == d)


SP, MA, PI = "스프린터", "마라토너", "파이오니어"
SCENE_BREAKS = {
    # 장면: (어떻게 깨나 — 그 장면의 전제나 결과 하나만)
    "s1-정지 표시 없음": ("s1", lambda st, W, c: _row(st, "A0", SP, W[8])["halted"].remove(c["E"])),
    "s2-G 를 안 들고 있음(P-3)": ("s2", lambda st, W, c: _row(st, "A0", SP, W[33])["marks"].pop(c["G"])),
    "s2-G 매도 신호 날이 다름": ("s2", lambda st, W, c: next(o for o in st["A1"][SP]["orders"] if o["code"] == c["G"]
                                                         and o["action"] == "매도").update(signal_date=W[36])),
    "s2-F 정지 중 평가가 바뀜": ("s2", lambda st, W, c: _row(st, "A1", SP, W[20])["marks"].update({c["F"]: 1.0})),
    "s3-H 매수 없음": ("s3", lambda st, W, c: _fills(st, "A0", SP).remove(next(
        f for f in _fills(st, "A0", SP) if f["date"] == W[25] and f["code"] == c["H"]))),
    "s4-현금 부족 보류 없음": ("s4", lambda st, W, c: st["A1"][MA]["skips"].clear()),
    "s5-남은 현금이 문턱 이상": ("s5", lambda st, W, c: _row(st, "A1", PI, W[12]).update(cash=1.0)),
    "s6-세율 경계 당일 세금이 다름(T5)": ("s6", lambda st, W, c: next(
        f for f in _fills(st, "A0", MA) if f["date"] == W[30] and f["code"] == c["B"]).update(tax=0.0)),
    "s6-그림자 서킷 누적 없음": ("s6", lambda st, W, c: [r.update(events=[e for e in r["events"]
                                                                   if not str(e.get("why", "")).startswith("누적")])
                                                        for a in h1.ARMS for tn in TR for r in st[a][tn]["days"]]),
    "s7-0주 아님": ("s7", lambda st, W, c: next(s for s in st["A0"][PI]["skips"] if s["code"] == c["Z"]).update(
        kind="현금부족")),
    "s7-Z 체결이 생김": ("s7", lambda st, W, c: _fills(st, "A1", PI).append(
        {"date": W[20], "code": c["Z"], "side": "buy", "kind": "stock", "purpose": "order"})),
}


@needs_r2
@pytest.mark.parametrize("name", list(SCENE_BREAKS))
def test_W3_장면_확인은_전제나_결과가_빠지면_실패(w3_result, tmp_path, name):
    """검토 5 P-3·P-9(T5): 장면 확인이 '늘 참'이 아니다 — 실제 W3 장부에서 한 가지만 깨면 그 장면만 실패."""
    res, _ = w3_result
    meta = RP.make_w3(tmp_path / "m")
    st = _w3_states(res)
    assert all(v["ok"] for v in RP.check_w3_scenes(st, meta).values())
    scene, brk = SCENE_BREAKS[name]
    brk(st, meta["W"], meta["codes"])
    out = RP.check_w3_scenes(st, meta)
    assert [k for k, v in out.items() if not v["ok"]] == [scene], {k: v["ok"] for k, v in out.items()}


@needs_r2
def test_M9_저장_읽기_지수_단위_hex_와_두_번째_실행_수(w3_result):
    """검토 5 P-9(T6·T21): 메모리의 지수 단위가 파일과 1ulp 만 달라도, 두 번째 실행 수가 봉 수보다 적어도, 두 번째 실행이
    0 이 아니어도 M9 실패."""
    res, _ = w3_result
    root = res["windows"]["W3-kr"]["root"]
    one = {"cal": ["2019-06-21"], "twice": [{"bar": "2019-06-21", "same": True, "code": 0}]}
    assert RP.check_m9(one, root, "kr", _w3_states(res))["ok"]
    st = _w3_states(res)
    tn = next(t for t in TR if st["A1"][t]["wallet"].holdings.get("KS200"))
    held = st["A1"][tn]["wallet"].holdings["KS200"]
    held.shares = math.nextafter(held.shares, math.inf)
    out = RP.check_m9(one, root, "kr", st)
    assert not out["ok"] and "지수 단위" in out["diffs"][0]
    short = {"cal": ["2019-06-20", "2019-06-21"], "twice": one["twice"]}
    assert not RP.check_m9(short, root, "kr", _w3_states(res))["ok"]
    bad = {"cal": one["cal"], "twice": [{"bar": "2019-06-21", "same": True, "code": 2}]}
    assert not RP.check_m9(bad, root, "kr", _w3_states(res))["ok"]


@needs_r2
def test_W3_일부_창은_기록하지_않고_보고서만_종료_코드_3(w3_result, tmp_path):
    res, _ = w3_result
    root = tmp_path / "h1"
    code = RP.finish(res, root, progress=lambda *a: None)
    assert code == RP.EXIT_PARTIAL == 3
    assert not (root / "replay_pass.json").exists()
    rep = list((root / "reports").glob("replay-*.md"))
    assert len(rep) == 1 and "통과 기록 없음" in rep[0].read_text(encoding="utf-8")
    assert (root / "reports" / (rep[0].stem + "-baseline.json")).read_bytes() == \
        Path(res["baseline_file"]).read_bytes()


@needs_r2
def test_W3_는_규칙을_바꾼_새_코드를_잡는다(tmp_path, monkeypatch):
    """쓸어 담기 문턱을 1 → 0.5 로 바꾸면(R2 는 1) s5 의 남은 현금 0.99 를 새 코드만 지수로 보내 M1 이 갈린다."""
    monkeypatch.setattr(h1, "SWEEP_MIN", 0.5)
    res = RP.replay(["W3"], RP.R2_REF, tmp_path / "w", progress=lambda *a: None)
    w = res["windows"]["W3-kr"]
    assert not w["ok"] and not res["passed"]
    assert not w["checks"]["M1"]["ok"] and not w["checks"]["S"]["ok"]


MUTATE_HALT = r'''
import json, sys
from pathlib import Path
copy, repo, work = sys.argv[1:4]
sys.path.insert(0, copy)
import h1_replay as RP
assert RP.__file__.startswith(copy), RP.__file__
res = RP.replay(["W3"], RP.R2_REF, work, repo=repo, progress=lambda *a: None)
w = res["windows"]["W3-kr"]
print(json.dumps({"passed": res["passed"], "checks": {m: c["ok"] for m, c in w["checks"].items()},
                  "m10": w["checks"]["M10"]["diffs"][:3], "m1": w["checks"]["M1"]["diffs"][:3]}, ensure_ascii=False))
'''


@needs_r2
def test_정지_중_판단_쉼과_L15_보유일수를_같이_틀린_코드도_W3_가_잡는다(tmp_path):
    """검토 5 P-2: team.py 의 '정지 중 판단 쉼'(continue)을 지우고 h1_check 의 L15 보유일수 확인도 끈 사본 — 예전 재현은 모두 같다고
    했다. 이제 M10(보유일수, 정지일도 셈)과 M1(가짜 브레인이 보유일수 31 에 팔아 매도 날이 달라짐)이 잡는다. 저장소 사본에서 따로 돈다."""
    code = tmp_path / "code"
    listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
    for f in listed.decode("utf-8").split("\0"):
        if f and not f.startswith(("state/", "docs/", "results/")) and (ROOT / f).is_file():
            (code / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / f, code / f)
    for name, old, new in (("team.py", '거래정지?)")\n            continue\n', '거래정지?)")\n'),
                           ("h1_check.py", '        if pos.get("days_held") != want:\n',
                            '        if False and pos.get("days_held") != want:\n')):
        src = (code / name).read_text(encoding="utf-8")
        assert src.count(old) == 1, name
        (code / name).write_text(src.replace(old, new), encoding="utf-8")
    p = subprocess.run([sys.executable, "-B", "-c", MUTATE_HALT, str(code), str(ROOT), str(tmp_path / "w")],
                       capture_output=True, text=True, timeout=900, cwd=tmp_path)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert not out["passed"]
    assert not out["checks"]["M10"] and any("보유일수" in d for d in out["m10"]), out
    assert not out["checks"]["M1"], out
    assert out["checks"]["M8"], "L15 보유일수 확인을 껐으므로 장부 점검은 통과 — 그래도 재현 비교(M10·M1)가 잡아야 한다"


@needs_r2
def test_K9_세율_줄_추가는_재현을_막지_않고_기록됨(tmp_path, monkeypatch, capsys):
    """검토 5 P-1 시나리오: ⑥-ii 로 h1.KR_SELL_TAX 끝에 ("2027-01-01", 0.0015) 를 더한 코드 — W3 재현이 K 까지 통과하고, 모든 창이
    같다는 결과로 기록·관문 열림까지 간다(W1·W2 는 손으로 만든 '같음' 결과, K9 확인은 창마다 같은 함수). 진행 표시(P-6)도 여기서 본다."""
    monkeypatch.setattr(h1, "KR_SELL_TAX", h1.KR_SELL_TAX + (("2027-01-01", 0.0015),))
    res = RP.replay(["W3"], RP.R2_REF, tmp_path / "w", progress=RP._say)
    w = res["windows"]["W3-kr"]
    assert w["ok"] and w["checks"]["K"]["ok"], w["checks"]["K"]
    out = capsys.readouterr().out
    assert "W3-kr: 25/45봉" in out and "25/45봉" not in Path(w["log"]).read_text(encoding="utf-8")
    full = _fake_result()
    full["windows"]["W3-kr"] = w
    full.update(baseline_file=res["baseline_file"], baseline_sha256=res["baseline_sha256"], r2_commit=res["r2_commit"])
    root = tmp_path / "h1"
    assert RP.finish(full, root, progress=lambda *a: None) == RP.EXIT_OK
    e = h1.replay_pass_entries(root)[0]
    assert e["ledger_fingerprints"]["W1-us"] == "f" * 64 and e["baseline_sha256"] == res["baseline_sha256"]
    h1.check_gate(root)


@needs_r2
def test_실데이터_W1_을_몇_봉으로_줄여도_기준값과_같음(tmp_path):
    specs = {n: dict(s, end="2026-06-10") for n, s in RP.WINDOWS.items() if s["group"] == "W1"}
    res = RP.replay(["W1"], RP.R2_REF, tmp_path / "w", progress=lambda *a: None, specs=specs)
    for n in ("W1-us", "W1-kr"):
        w = res["windows"][n]
        assert w["n_bars"] >= 6 and w["S"] == "2026-06-01" and w["last"] == "2026-06-10", (n, w["n_bars"], w["S"])
        assert w["ok"], {m: c["detail"] for m, c in w["checks"].items() if not c["ok"]}
        assert w["checks"]["M10"]["ok"]
    assert not res["complete"]                                                    # 창을 바꿨으므로 기록 대상 아님


# ============================ 기록 갈래 ============================

def _fake_result(passed=True, complete=True, code_changed=False):
    ch, files = h1.code_hash()
    env = h1.env_info()
    win = {}
    for n, s in RP.WINDOWS.items():
        checks = {m: RP._chk(True, "같음") for m in RP.REQUIRED[s["group"]]}
        if not passed and n == "W2-kr":
            checks["M1"] = RP._chk(False, "체결 차이", ["A1: 가짜 차이"])
        win[n] = {"spec": s, "checks": checks, "ok": passed or n != "W2-kr", "run": {"seconds": 1.0, "max_run_s": 0.1},
                  "n_bars": 3, "S": s["start"], "last": s["end"], "fingerprint": "f" * 64 if n != "W3-kr" else "e" * 64,
                  "warnings": {}, "ref": {}}
    return {"code_hash": ch, "files": files, "env": env, "code_changed": code_changed, "r2_ref": RP.R2_REF,
            "r2_commit": "0" * 40, "modules": {"sim_team": "x"}, "windows": win, "groups": ["W1", "W2", "W3"],
            "complete": complete, "passed": passed, "seconds": 1.0, "baseline_seconds": 0.5,
            "started_at": "2026-11-05T10:00:00+09:00"}


def _with_baseline(res, tmp_path):
    blob = json.dumps({"가짜": "하네스 결과"}, ensure_ascii=False).encode("utf-8")
    f = tmp_path / "harness_out.json"
    f.write_bytes(blob)
    res.update(baseline_file=str(f), baseline_sha256=hashlib.sha256(blob).hexdigest())
    return res, blob


def test_통과면_보고서_먼저_그다음_기록_그다음_기록함_관문이_그_줄로_열림(tmp_path, monkeypatch):
    """검토 5 P-5·P-8: 보고서(기록할 줄의 내용까지, '기록 전')를 먼저 쓰고 → replay_pass.json 한 줄 → 보고서를 '기록함'으로.
    줄에는 started_at(재현 시작)·passed_at(기록 때)·기준값 결과 파일과 sha256·R2 커밋."""
    root = tmp_path / "h1"
    r2rep = tmp_path / "r2rep"
    (r2rep / "data" / "rates").mkdir(parents=True)
    (r2rep / "data" / "rates" / "us_tbill.csv").write_text("date,rate_pct,source\n2026-01-02,3.6,s\n", encoding="utf-8")
    (r2rep / "data" / "rates" / "kr_shortrate.csv").write_text("date,rate_pct,source\n2026-01-01,2.5,s\n",
                                                               encoding="utf-8")
    (root / "rates").mkdir(parents=True)
    (root / "rates" / "kr_shortrate.csv").write_text("이미 있음", encoding="utf-8")   # 있으면 덮지 않는다
    seen = {}
    real = h1.record_replay_pass

    def spy(entry, r=None):
        reps = sorted((Path(r) / "reports").glob("replay-*.md"))
        seen["report"] = reps[0].read_text(encoding="utf-8") if len(reps) == 1 else None
        seen["baseline"] = sorted((Path(r) / "reports").glob("*-baseline.json"))
        return real(entry, r)
    monkeypatch.setattr(h1, "record_replay_pass", spy)
    res, blob = _with_baseline(_fake_result(), tmp_path)
    t0 = datetime.now().astimezone()
    code = RP.finish(res, root, r2rep, progress=lambda *a: None)
    assert code == RP.EXIT_OK
    entries = h1.replay_pass_entries(root)
    assert len(entries) == 1
    e = entries[0]
    assert e["code_hash"] == h1.code_hash()[0] and e["files"] == h1.code_hash()[1]
    assert e["ledger_fingerprints"] == {"W1-us": "f" * 64, "W1-kr": "f" * 64, "W2-kr": "f" * 64}
    assert e["data_golden_sha256"] == h1.data_golden_digest() and e["fingerprint_version"] == h1.FINGERPRINT_VERSION
    assert e["report"].startswith("reports/replay-") and (root / e["report"]).exists()
    assert e["started_at"] == res["started_at"]
    assert t0.replace(microsecond=0) <= datetime.fromisoformat(e["passed_at"]) <= datetime.now().astimezone()
    assert e["baseline"] == e["report"][:-3] + "-baseline.json" and (root / e["baseline"]).read_bytes() == blob
    assert e["baseline_sha256"] == hashlib.sha256(blob).hexdigest()
    assert e["r2_commit"] == res["r2_commit"] and e["windows"] == sorted(RP.WINDOWS)
    # 순서: 기록하는 순간 보고서·기준값 파일이 이미 있었고(기록할 줄의 code_hash 까지), 상태는 '기록 전'
    assert seen["report"] is not None and "기록 전" in seen["report"] and e["code_hash"] in seen["report"]
    assert e["baseline_sha256"] in seen["report"] and len(seen["baseline"]) == 1
    after = (root / e["report"]).read_text(encoding="utf-8")
    assert "기록함 — replay_pass.json 1번째 줄" in after and "기록 전" not in after and e["passed_at"] in after
    h1.check_gate(root)                                                          # 이 줄로 관문이 열린다(거절 없음)
    assert (root / "rates" / "us_tbill.csv").exists()
    assert (root / "rates" / "kr_shortrate.csv").read_text(encoding="utf-8") == "이미 있음"
    changes = h1.read_jsonl(root / "changes.jsonl")
    assert [c["kind"] for c in changes] == ["replay-pass"]


def test_기록이_거절되면_보고서에_기록_실패_환경_문제(tmp_path, monkeypatch):
    def refuse(entry, r=None):
        raise h1.H1Refused(3, "통과 기록이 봉인과 맞지 않음")
    monkeypatch.setattr(h1, "record_replay_pass", refuse)
    root = tmp_path / "h1"
    with pytest.raises(RP.ReplayEnvError, match="통과 기록을 쓰지 못함"):
        RP.finish(_fake_result(), root, progress=lambda *a: None)
    rep = next((root / "reports").glob("replay-*.md")).read_text(encoding="utf-8")
    assert "기록 실패(종료 코드 3)" in rep and "기록함" not in rep
    assert not (root / "replay_pass.json").exists()


@pytest.mark.parametrize("kw,want", [({"passed": False}, RP.EXIT_DIFF), ({"code_changed": True}, RP.EXIT_ENV),
                                     ({"complete": False}, RP.EXIT_PARTIAL)])
def test_실패_코드바뀜_일부는_기록_없음(tmp_path, kw, want):
    root = tmp_path / "h1"
    lines = []
    code = RP.finish(_fake_result(**kw), root, progress=lines.append)
    assert code == want
    assert not (root / "replay_pass.json").exists() and not (root / "rates").exists()
    rep = list((root / "reports").glob("replay-*.md"))
    assert len(rep) == 1
    if kw.get("passed") is False:
        assert any("W2-kr M1" in x for x in lines)                               # 차이 표를 화면에
        text = rep[0].read_text(encoding="utf-8")
        assert "통과 아님" in text and "A1: 가짜 차이" in text                    # 어떤 M 항목·어떤 열쇠인지 보고서에


def test_자료_받기_골든이_깨지면_기록하지_않음(tmp_path, monkeypatch):
    """검토 5 P-9(T4): 모든 창이 같아도 자료 받기 골든이 저장본과 다르면 통과 기록을 남기지 않는다."""
    monkeypatch.setattr(RP, "data_golden_ok", lambda: RP._chk(False, "자료 받기 골든 결과가 저장본과 다름", ["다름"]))
    root = tmp_path / "h1"
    assert RP.finish(_fake_result(), root, progress=lambda *a: None) == RP.EXIT_DIFF
    assert not (root / "replay_pass.json").exists()
    assert "자료 받기 골든 결과가 저장본과 다름" in next((root / "reports").glob("replay-*.md")).read_text(encoding="utf-8")


def test_기록_직전_코드가_바뀌면_기록하지_않음(tmp_path):
    res = _fake_result()
    res["code_hash"] = "0" * 64                                                   # 재현 때 지문 ≠ 지금 지문
    root = tmp_path / "h1"
    assert RP.finish(res, root, progress=lambda *a: None) == RP.EXIT_ENV
    assert not (root / "replay_pass.json").exists()


def test_cli_인자_오류는_9_도움말에_종료_코드(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    assert RP.cli(["--windows", "W4"]) == RP.EXIT_USAGE
    assert RP.cli(["--windows", "W1,W1"]) == RP.EXIT_USAGE
    assert RP.cli(["--root", str(ROOT / "state")]) == RP.EXIT_USAGE              # 운영 상태 폴더는 거절
    assert RP.cli(["--없는-옵션"]) == RP.EXIT_USAGE
    text = RP._parser().format_help()
    for k in (0, 2, 3, 4, 9, 130):
        assert f"{k:>3}  {RP.EXIT_TEXT[k]}" in text                                # 한 줄에 하나씩
    assert (RP.EXIT_OK, RP.EXIT_DIFF, RP.EXIT_PARTIAL, RP.EXIT_ENV, RP.EXIT_USAGE, RP.EXIT_INTERRUPT) == (0, 2, 3, 4, 9, 130)


def test_cli_R2_가_없으면_4_임시_폴더는_남기고_경로를_알림(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert RP.cli(["--root", str(tmp_path / "h1"), "--windows", "W3", "--r2-ref", "refs/없는/가지-12345"]) == RP.EXIT_ENV
    assert not (tmp_path / "h1" / "replay_pass.json").exists()
    kept = list(tmp_path.glob("h1-replay-*"))
    assert len(kept) == 1                                                        # 실패면 원인 확인용으로 남김(검토 5 P-8)
    out = capsys.readouterr().out
    assert f"임시 폴더를 남겨 둠(원인 확인용): {kept[0]}" in out and "끝: 종료 코드 4" in out


def test_cli_일부_창이_같으면_3_임시_폴더는_지움(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setattr(RP, "replay", lambda groups, ref, work, **k: _fake_result(complete=False))
    assert RP.cli(["--root", str(tmp_path / "h1"), "--windows", "W3"]) == RP.EXIT_PARTIAL
    assert not list(tmp_path.glob("h1-replay-*")) and not (tmp_path / "h1" / "replay_pass.json").exists()
