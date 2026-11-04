"""
sim_team.py 점검 (인터넷 없이 data/ 만 사용). PASS/FAIL 을 찍고, 하나라도 FAIL 이면 종료 코드 1.

점검 목록
  1. R0 동등성: 트레이너 1명·종목 1개·MAX_POSITIONS=1·상한 100%·현금·이자 0·미국 비용에서
     거래 목록·일별 평가액·최종 가치가 R0 sim.simulate() 와 같다 (R0 sim.py 는 git 에서 임시 폴더로 꺼내 import)
  2. 판단 창 동등성(국내): 최근 80봉만 넘긴 판단 = 매 봉 그날까지 지표를 새로 계산해 전부 넘긴 판단
  3. 미리보기 없음: 데이터를 t 이후 잘라도 t 까지의 체결·주문·보류·일별 평가가 그대로 (여러 t, 미국·국내·H4)
  4. 장부: 현금 ≥ -0.01, 지수 단위 ≥ 0, 평가 = 현금+주식+지수(매 종가), 현금·단위 원장, 체결마다 비용식,
     t+1 시가 체결, 국내 Volume=0 날 체결 없음 (실데이터 스모크 결과 전부에 대해)
  5. 거래 0번인 A1 = 지수 B&H − 첫 매수 비용 / A2 의 70% = 지수 B&H
  6. 국내 매도세: 세율 경계 날짜마다 합성 매도(전날·당일), 지수 다리는 세금 0, 끝 평가의 세금
  7. 국내 Volume=0: 그날 신호·체결 없음, 미뤄진 주문은 다음 거래된 봉에, 대기 주문도 자리로 셈, days_held 는 거래된 봉만
  8. 이자: A1(전 거래일 값, 빈 날 이월) / A2(m월 = m-1월 값, 없으면 이월)
  9. 월말 10개월선 전환 날짜(A1-T·G11)
 10. 단계적 서킷(H3): -10% 절반 상한, -20% 정리·20거래일 쉼·고점 재설정·절반 재개, 새 고점 → 원래 상한,
     하루 -7% 영구 정지(A1 → 정리 대금은 지수로), 지금 서킷(누적 -10%)
 11. H4: 공식·n<20 이면 60/30/10·클램프, 실데이터 재배분 몫 재계산, 옮긴 금액 합 0, 월 수익률 재계산, 짧은 국면은 A1 과 같음
 12. 무작위 대조: 모든 거래를 제자리에 두면 실제 합과 같음, 같은 시드 재현, 범위 안, 거래 하나 손계산
 13. 스모크: (us, us_pit, kr) × (A0, A1, A1T, A2, G11, A0/A1 × 서킷 2종, A1+H4) × 2018 국면 — 예외·NaN 없음, 4번 장부 점검

실행(저장소 루트에서):
    /root/.venv-cs/bin/python -I reports/research-r2-2026-11-04/check_team.py
"""
from __future__ import annotations

import importlib.util
import math
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (str(ROOT), str(HERE)):          # -I 로 실행하므로 저장소 모듈·sim_team 경로를 직접 넣는다
    if p not in sys.path:
        sys.path.insert(0, p)

import sim_team as S                      # noqa: E402
from paper_wallet import shares_within_cap  # noqa: E402

RESULTS: list = []


def check(name: str, ok, detail: str = ""):
    ok = bool(ok)
    RESULTS.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def section(fn):
    def wrap(*a, **k):
        t = time.time()
        print(f"\n=== {fn.__doc__.strip().splitlines()[0]} ===", flush=True)
        try:
            out = fn(*a, **k)
        except Exception:
            traceback.print_exc()
            check(f"{fn.__name__}: 예외 없이 끝남", False)
            out = None
        print(f"    ({time.time() - t:.1f}s)", flush=True)
        return out
    return wrap


def close(a, b, rel=1e-9, abs_=1e-6):
    return abs(a - b) <= abs_ + rel * max(abs(a), abs(b))


# ---------------------------------------------------------------- 합성 데이터 도구
class Scripted:
    """합성 점검용 가짜 브레인: 데이터의 'Sig' 칸을 따른다(+1 = 보유 없을 때 매수, -1 = 보유 중 매도).
    'Sig' 칸이 없으면 절대 사지 않는다(거래 0번 점검용). 불린 날짜·days_held 를 calls 에 남긴다."""
    calls: list = []

    def add_indicators(self, df):
        return df.copy()

    def decide(self, df, position):
        d = df.index[-1].date().isoformat()
        Scripted.calls.append((d, None if position is None else position["days_held"]))
        sig = float(df["Sig"].iloc[-1]) if "Sig" in df.columns else 0.0
        if position is None:
            return ("매수", "합성 매수") if sig > 0 else ("관망", "합성 관망")
        return ("매도", "합성 매도") if sig < 0 else ("관망", "합성 보유")


SCRIPTED = {t: Scripted for t in S.TRAINERS}


def synth_market(key, cal, idx_close, stocks, rates=None, rule=None, idx_open=None):
    """stocks = {code: {"close": arr, "open": arr(없으면 전날 종가), "sig": arr, "vol0": [봉 위치]}}"""
    idx_close = np.asarray(idx_close, float)
    idx_open = np.asarray(idx_open if idx_open is not None else idx_close, float)
    idx = pd.DataFrame({"Open": idx_open, "High": np.maximum(idx_open, idx_close),
                        "Low": np.minimum(idx_open, idx_close), "Close": idx_close, "Volume": 1e6}, index=cal)
    frames, zv = {}, {}
    for code, sp in stocks.items():
        c = np.asarray(sp["close"], float)
        o = np.asarray(sp["open"], float) if "open" in sp else np.concatenate(([c[0]], c[:-1]))
        df = pd.DataFrame({"Open": o, "High": np.maximum(o, c), "Low": np.minimum(o, c), "Close": c,
                           "Volume": 1000.0, "Sig": np.asarray(sp.get("sig", np.zeros(len(c))), float)}, index=cal)
        for k in sp.get("vol0", []):                     # 실제 국내 정지 행처럼: 시가·고가·저가 0, 종가 = 전날, 거래량 0
            df.iloc[k, df.columns.get_loc("Open")] = 0.0
            df.iloc[k, df.columns.get_loc("High")] = 0.0
            df.iloc[k, df.columns.get_loc("Low")] = 0.0
            df.iloc[k, df.columns.get_loc("Close")] = df["Close"].iloc[k - 1]
            df.iloc[k, df.columns.get_loc("Volume")] = 0.0
        if key == "kr":
            zv[code] = {d.date().isoformat() for d in df.index[df["Volume"] == 0]}
            df = S.drop_zero_volume(df)                  # load_frames 와 같은 함수(A5)
        frames[code] = df
    if rates is None:
        rates = pd.Series([0.0], index=pd.DatetimeIndex([cal[0] - pd.Timedelta(days=40)]))
        rule = "prev_day" if key.startswith("us") else "prev_month"
    return S.MarketData(key, idx, frames, rates, rule, brains=SCRIPTED, zero_volume=zv)


def one_trainer(**kw):
    base = dict(trainers=("마라토너",), ratios={"마라토너": 1.0}, with_refs=False)
    base.update(kw)
    return S.Config(**base)


# ---------------------------------------------------------------- 4. 장부 점검 (모든 결과에 공통)
def accounting(res, md, tag):
    """현금·단위·평가·원장·비용식·t+1 시가·Volume=0 점검. 문제 목록을 돌려준다."""
    bad = []
    d = res["daily"]
    num = d.select_dtypes(include=[float, int])
    if num.isna().any().any() or np.isnan(res["equity"]).any():
        bad.append("NaN")
    for name, sv in res["sleeves"].items():
        v, st, ix, ca = (d[f"{k}_{name}"].to_numpy(float) for k in ("v", "stock", "index", "cash"))
        if ca.min() < -0.01:
            bad.append(f"{name} 현금 음수 {ca.min()}")
        if ix.min() < 0 or sv["units_end"] < 0:
            bad.append(f"{name} 지수 단위 음수")
        if np.max(np.abs(v - (st + ix + ca)) / np.maximum(1, v)) > 1e-9:
            bad.append(f"{name} 평가 ≠ 현금+주식+지수")
        fl = [f for f in res["fills"] if f["sleeve"] == name]
        ledger = sv["start_cash"] + sum(f["cash"] for f in fl) + sv["interest"]
        if not close(ledger, sv["cash_end"], 1e-9, 1e-6):
            bad.append(f"{name} 현금 원장 {ledger} vs {sv['cash_end']}")
        units = sum((f["qty"] if f["side"] == "매수" else -f["qty"]) for f in fl if f["kind"] == "index")
        if not close(units + sv["units_moved"], sv["units_end"], 1e-9, 1e-9):
            bad.append(f"{name} 지수 단위 원장")
    tot = sum(d[f"v_{n}"] for n in res["sleeves"])
    if np.max(np.abs(tot - d["value"]) / d["value"]) > 1e-12:
        bad.append("합계 ≠ 슬리브 합")
    # 체결마다 비용식 (PaperWallet 식: 매수 = 가격×(1+슬리피지)×수량×(1+수수료), 매도 = 가격×(1-슬리피지)×수량×(1-수수료-세금))
    for f in res["fills"]:
        px, q = f["price"], f["qty"]
        if f["side"] == "매수":
            ex = px * (1 + md.slip) * q
            want = -(ex + ex * md.fee)
        else:
            tax = 0.0 if f["kind"] == "index" else expected_tax(md.key, f["date"])
            pr = px * (1 - md.slip) * q
            want = pr - pr * md.fee - pr * tax
            if not close(f["tax"], pr * tax, 1e-12, 1e-9):
                bad.append(f"세금 {f}")
        if not close(f["cash"], want, 1e-12, 1e-6):
            bad.append(f"비용식 {f}")
    # t+1 시가 체결 (그 종목의 '신호 다음 봉' 시가), 국내 Volume=0 날 체결 없음
    for tr in res["trades"]:
        st = md.by_code[tr["code"]]
        pos = {x: j for j, x in enumerate(st.dates)}
        for sig, own, px in ((tr["signal_date"], tr["entry_own"], tr["entry_price"]),
                             (tr.get("exit_signal_date"), tr["exit_own"], tr["exit_price"])):
            if own is None:
                continue
            if pos[sig] + 1 != own or px != st.open[own] or st.dates[own] <= sig:
                bad.append(f"t+1 시가 아님 {tr['code']} {sig}->{st.dates[own]}")
        for dd in (tr["entry_date"], tr["exit_date"]):
            if dd and dd in md.zero_volume.get(tr["code"], set()):
                bad.append(f"Volume=0 날 체결 {tr['code']} {dd}")
    if res["metrics"]["open_fallbacks"]:
        bad.append("시가 대신 종가 체결")
    return bad


def expected_tax(key, date):
    """STAGE0 §1.2 표를 점검 쪽에서 따로 적은 것(sim_team 의 표와 독립)."""
    if not key.startswith("kr"):
        return 0.0
    if date < "2019-06-03":
        return 0.0030
    if date < "2021-01-01":
        return 0.0025
    if date < "2023-01-01":
        return 0.0023
    if date < "2024-01-01":
        return 0.0020
    if date < "2025-01-01":
        return 0.0018
    if date < "2026-01-01":
        return 0.0015
    return 0.0020


# ================================================================ 1. R0 동등성
@section
def c_r0_equivalence():
    """1. R0 sim.simulate() 와 같은가 (퇴화 설정)"""
    src = subprocess.run(["git", "-C", str(ROOT), "show",
                          "origin/research-2026-11-04:reports/research-2026-11-04/sim.py"],
                         capture_output=True, check=True).stdout
    tmp = Path(tempfile.mkdtemp(prefix="r0sim_"))
    (tmp / "r0").mkdir()
    (tmp / "r0" / "sim.py").write_bytes(src)
    saved = list(sys.path)
    spec = importlib.util.spec_from_file_location("r0_sim", tmp / "r0" / "sim.py")
    r0 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r0)
    sys.path[:] = saved                                   # R0 가 넣은 임시 경로는 뺀다
    md = S.get_market("us")
    n = bad = 0
    for code in ["AAPL", "TSLA", "XOM", "COST"]:
        df = md.by_code[code].df
        for tname, cls in S.team.BRAINS.items():
            prep = r0.Prepared(df, cls)
            for per in ["2015-17 상승", "2018 조정", "2022 하락"]:
                s, e = S.REGIMES[per]
                i0, i1 = r0.idx_range(prep.dates, s, e)
                a = r0.simulate(prep, cls(), i0, i1, 10_000, 1.0, code)
                b = S.run(S.Config(market="us", period=per, arm="A0", trainers=(tname,), ratios={tname: 1.0},
                                   caps={tname: 1.0}, universe=(code,), max_positions=1, interest=False,
                                   cap_base="cash", total=10_000, with_refs=False))
                ta = [(int(x), None if y is None else int(y)) for x, y in a["trades"]]
                tb = [(t["entry_own"], t["exit_own"]) for t in b["trades"]]
                eq_ok = np.allclose(np.asarray(a["equity"]), b["equity"], rtol=0, atol=1e-6)
                ok = (ta == tb and (i0, i1) == (b["i0"], b["i1"]) and close(10_000 + a["profit"], b["final"], 0, 1e-6)
                      and eq_ok and a["buys"] == b["metrics"]["buys"] and a["skips"] == b["metrics"]["skips"])
                n += 1
                if not ok:
                    bad += 1
                    print(f"   불일치 {code} {tname} {per}: R0 {len(ta)}거래 {10_000 + a['profit']:.4f} / "
                          f"R2 {len(tb)}거래 {b['final']:.4f}")
    check("R0 동등성: 4종목 × 3트레이너 × 3국면 거래 목록·일별 평가·최종 가치·매수·보류 수 일치", bad == 0,
          f"{n - bad}/{n} 일치")


# ================================================================ 2. 판단 창 동등성 (국내)
@section
def c_window_kr():
    """2. 국내: 최근 80봉 판단 = 그날까지 지표를 새로 계산해 전부 넘긴 판단"""
    md = S.get_market("kr")
    n = bad = 0
    for code, js in (("373220", range(15, 140)), ("005930", range(905, 990)), ("207940", range(1000, 1060))):
        st = md.by_code[code]
        for tname, cls in S.team.BRAINS.items():
            brain = cls()
            for j in js:
                full = brain.add_indicators(st.df.iloc[: j + 1])
                slow = S.ACT[brain.decide(full, None)[0]]
                fast = md.flat_action(tname, st, j)
                pos = {"buy_price": float(st.open[max(0, j - 3)]), "days_held": 3, "shares": 1}
                w = st.ind[tname].iloc[max(0, j - S.WINDOW + 1): j + 1]
                h_slow = brain.decide(full, pos)[0]
                h_fast = brain.decide(w, pos)[0]
                n += 2
                bad += (slow != fast) + (h_slow != h_fast)
    check("국내 3종목(신규상장·거래정지 포함) × 3트레이너: 보유 없음/보유 중 판단 불일치 0", bad == 0, f"{n}개 판단 비교")


# ================================================================ 3. 미리보기 없음
def same_prefix(full, tr, tdate):
    probs = []

    def eqd(a, b):
        if a.keys() != b.keys():
            return False
        for k in a:
            x, y = a[k], b[k]
            if isinstance(x, float) or isinstance(y, float):
                if not (x == y or (isinstance(x, float) and isinstance(y, float) and close(x, y, 1e-12, 1e-9))):
                    return False
            elif isinstance(x, dict):
                if not eqd(x, y):
                    return False
            elif x != y:
                return False
        return True
    fa = [f for f in full["fills"] if f["date"] <= tdate]
    if len(fa) != len(tr["fills"]) or not all(eqd(a, b) for a, b in zip(fa, tr["fills"])):
        probs.append("체결")
    oa = [o for o in full["orders"] if o["signal_date"] < tdate]
    if len(oa) != len(tr["orders"]) or not all(eqd(a, b) for a, b in zip(oa, tr["orders"])):
        probs.append("주문")
    sa = [x for x in full["skips"] if x["date"] <= tdate]
    if sa != tr["skips"]:
        probs.append("보류")

    def ev_keep(e):
        return e["date"] < tdate or (e["kind"] == "H4" and e["date"] == tdate)
    ea = [e for e in full["events"] if ev_keep(e)]
    eb = [e for e in tr["events"] if ev_keep(e)]
    if len(ea) != len(eb) or not all(eqd(a, b) for a, b in zip(ea, eb)):
        probs.append("이벤트")
    da = full["daily"].loc[:tdate]
    db = tr["daily"]
    if list(da.index) != list(db.index):
        probs.append("날짜")
    else:
        for c in db.columns:
            x, y = da[c].to_numpy(), db[c].to_numpy()
            if x.dtype.kind in "fi":
                if not np.allclose(x.astype(float), y.astype(float), rtol=1e-12, atol=1e-9):
                    probs.append(f"일별 {c}")
            elif list(x) != list(y):
                probs.append(f"일별 {c}")
    return probs


@section
def c_lookahead():
    """3. 미리보기 없음: t 이후 데이터를 잘라도 t 까지 결과가 같다"""
    plans = [
        ("us", "2020 급락·회복", [dict(arm="A0", cb="current"), dict(arm="A1", cb="staged"), dict(arm="A1T"),
                                  dict(arm="A2")], [30, "2020-03-31", 100, 200]),       # 2020-03-31 = 월말
        ("kr", "2018 조정", [dict(arm="A0", cb="staged"), dict(arm="A1T")],
         ["2018-05-02", "2018-10-10", "2018-10-31", 230]),                                # 05-02 = 005930 정지 중
    ]
    for key, per, arms, cuts in plans:
        md = S.get_market(key)
        i0, i1 = S.period_range(md, per)
        fulls = [S.run(S.Config(market=key, period=per, with_refs=False, **a)) for a in arms]
        for cut in cuts:
            t = i0 + cut if isinstance(cut, int) else int(md.cal.searchsorted(pd.Timestamp(cut)))
            tdate = md.dstr[t]
            idx, frames, rates, rule, zv = S.load_frames(key, tdate)
            mdt = S.MarketData(key, idx, frames, rates, rule, zero_volume=zv)     # 새 캐시(판단도 잘린 데이터로 다시)
            for a, full in zip(arms, fulls):
                tr = S.run(S.Config(market=key, period=(S.REGIMES[per][0], tdate), with_refs=False, **a), mdt)
                probs = same_prefix(full, tr, tdate)
                check(f"미리보기 없음 {key} {per} {S.label(S.Config(**a))} t={tdate}", not probs, ",".join(probs))
    # H4: 첫 재배분 이후로 잘라 본다 (2015-17, 미국)
    key, per = "us", "2015-17 상승"
    md = S.get_market(key)
    full = S.run(S.Config(market=key, period=per, arm="A1", realloc=True, with_refs=False))
    ch = [e["date"] for e in full["events"] if e["kind"] == "H4" and e["changed"]]
    check("H4 2015-17 에 실제 재배분이 있다(뒤 점검이 의미 있게)", len(ch) >= 1, f"재배분 {len(ch)}번, 처음 {ch[:1]}")
    for tdate in (ch[0], md.dstr[int(md.cal.searchsorted(pd.Timestamp(ch[0]))) + 60]) if ch else ():
        idx, frames, rates, rule, zv = S.load_frames(key, tdate)
        mdt = S.MarketData(key, idx, frames, rates, rule, zero_volume=zv)
        tr = S.run(S.Config(market=key, period=(S.REGIMES[per][0], tdate), arm="A1", realloc=True, with_refs=False),
                   mdt)
        probs = same_prefix(full, tr, tdate)
        check(f"미리보기 없음 us {per} A1+H4 t={tdate}", not probs, ",".join(probs))


# ================================================================ 5. 거래 0번 A1 = 지수 B&H, A2 의 70% = 지수 B&H
@section
def c_index_identities():
    """5. 거래 0번 A1 = 지수 B&H − 첫 매수 비용, A2 의 70% = 지수 B&H"""
    idx, frames, rates, rule, zv = S.load_frames("us")
    mdn = S.MarketData("us", idx, frames, rates, rule, brains=SCRIPTED)      # 'Sig' 없음 → 절대 안 삼
    per = "2018 조정"
    i0, i1 = S.period_range(mdn, per)
    r = S.run(S.Config(market="us", period=per, arm="A1", with_refs=False), mdn)
    total = r["total"]
    unit_cost = mdn.idx_open[i0] * (1 + mdn.slip) * (1 + mdn.fee)
    expect = total / unit_cost * mdn.idx_close[i0:i1 + 1]
    got = r["daily"]["value"].to_numpy()
    check("거래 0번 A1: 주식 체결 0, 지수 다리 = 첫날 3건", r["metrics"]["buys"] == 0 and r["metrics"]["index_legs"] == 3)
    check("거래 0번 A1: 매 종가 = 총액 × 종가 / (첫 시가 × (1+슬리피지)(1+수수료)) (남는 현금 < 1)",
          np.max(np.abs(got - expect)) < 3.0, f"최대 차이 {np.max(np.abs(got - expect)):.2e}")
    fin = total / unit_cost * mdn.idx_close[i1] * (1 - mdn.slip) * (1 - mdn.fee)
    check("거래 0번 A1: 최종 = 위 값 × (1-슬리피지)(1-수수료)", abs(r["final"] - fin) < 3.0, f"차이 {r['final'] - fin:.2e}")
    ri = S.run(S.Config(market="us", period=per, arm="IDX", with_refs=False), mdn)
    check("거래 0번 A1 = IDX(지수 소수 단위 B&H) 매일", np.max(np.abs(got - ri["daily"]["value"].to_numpy())) < 3.0)
    bh = S.index_buy_hold(mdn, i0, i1, total)
    check("거래 0번 A1 ≈ R0 방식 지수 B&H(정수 단위) — 차이 < 지수 1단위 값", abs(r["final"] - (total * (1 + bh["return"])))
          < unit_cost + 3.0, f"차이 {r['final'] - total * (1 + bh['return']):.2f}")
    # A2 (실제 브레인)
    md = S.get_market("us")
    r2 = S.run(S.Config(market="us", period=per, arm="A2", with_refs=False), md)
    v70 = r2["daily"]["v_지수70%"].to_numpy()
    e70 = 0.7 * total / unit_cost * md.idx_close[i0:i1 + 1]
    check("A2 지수70%: 매 종가 = 70% × 지수 B&H, 체결은 첫날 1건뿐",
          np.max(np.abs(v70 - e70)) < 1.0 and sum(1 for f in r2["fills"] if f["sleeve"] == "지수70%") == 1,
          f"최대 차이 {np.max(np.abs(v70 - e70)):.2e}")
    check("A2 지수70% 최종 = 0.7 × IDX 최종", abs(r2["finals"]["지수70%"] - 0.7 * ri["final"]) < 1.0)


# ================================================================ 6. 국내 매도세 (합성)
@section
def c_kr_tax():
    """6. 국내 매도세: 세율 경계 날짜마다 합성 매도, 지수 다리 세금 0"""
    cal = pd.bdate_range("2018-09-03", "2026-03-31")
    n = len(cal)
    bounds = ["2019-06-03", "2021-01-01", "2023-01-01", "2024-01-01", "2025-01-01", "2026-01-01"]
    fill_days = []
    for b in bounds:
        k = int(cal.searchsorted(pd.Timestamp(b)))
        fill_days += [k - 1, k]                       # 경계 전날 / 경계 당일(또는 그 뒤 첫 거래일)
    stocks = {}
    for m, k in enumerate(fill_days):
        sig = np.zeros(n)
        sig[k - 8] = 1                               # k-7 시가에 사고
        sig[k - 1] = -1                              # k 시가에 판다
        stocks[f"S{m:02d}"] = {"close": np.full(n, 10_000.0), "open": np.full(n, 10_010.0), "sig": sig}
    sig = np.zeros(n)
    sig[n - 20] = 1
    stocks["HOLD"] = {"close": np.full(n, 20_000.0), "open": np.full(n, 20_020.0), "sig": sig}  # 끝까지 보유
    md = synth_market("kr", cal, np.full(n, 300.0), stocks, idx_open=np.full(n, 300.3))
    r = S.run(one_trainer(market="kr", period=(cal[60].date().isoformat(), cal[-1].date().isoformat()), arm="A1",
                          caps={"마라토너": 0.05}, interest=False, total=100_000_000), md)
    sells = [f for f in r["fills"] if f["kind"] == "stock" and f["side"] == "매도"]
    want_dates = [cal[k].date().isoformat() for k in fill_days]
    ok_dates = sorted(f["date"] for f in sells) == sorted(want_dates)
    ok_tax = all(close(f["tax"], f["price"] * (1 - md.slip) * f["qty"] * expected_tax("kr", f["date"]), 1e-12, 1e-9)
                 for f in sells)
    detail = ", ".join(f"{f['date']}:{f['tax'] / (f['price'] * (1 - md.slip) * f['qty']) * 100:.2f}%" for f in
                       sorted(sells, key=lambda x: x["date"]))
    check("국내 매도세: 경계 6곳 전날·당일 매도 12건이 §1.2 세율", ok_dates and ok_tax, detail)
    idx_sells = [f for f in r["fills"] if f["kind"] == "index" and f["side"] == "매도"]
    check("지수(KS200) 다리 매도세 0", idx_sells and all(f["tax"] == 0.0 for f in idx_sells), f"{len(idx_sells)}건")
    bad = accounting(r, md, "kr_tax")
    check("합성 국내 장부 점검", not bad, "; ".join(bad[:3]))
    sv = r["sleeves"]["마라토너"]
    pos_hold = [t for t in r["trades"] if t["exit_date"] is None]
    pr = 20_000.0 * (1 - md.slip) * pos_hold[0]["shares"]
    fin = sv["cash_end"] + pr - pr * md.fee - pr * expected_tax("kr", cal[-1].date().isoformat())
    u = sv["units_end"] * 300.0 * (1 - md.slip)
    fin += u - u * md.fee
    check("국내 끝 평가: 보유 주식은 끝 날짜 세율(0.20%)까지 빼고, 지수는 세금 없이", close(fin, r["final"], 1e-12, 1e-6))


# ================================================================ 7. 국내 Volume=0 (합성)
@section
def c_kr_zero_volume():
    """7. 국내 Volume=0: 신호·체결 없음, 다음 거래된 봉으로, 자리 셈, days_held"""
    cal = pd.bdate_range("2022-01-03", periods=150)
    n = len(cal)
    a_sig = np.zeros(n)
    a_sig[79] = 1          # 79 종가 매수 신호 → 80·81·82 정지 → 83 시가 체결
    a_sig[95] = -1         # 95 종가 매도 신호 → 96·97 정지 → 98 시가 체결
    a_close = 100 + np.arange(n) * 0.1
    b_sig = np.zeros(n)
    b_sig[80:83] = 1       # A 의 매수 대기 중(80~82)에 B 신호 → 자리 없음(MAX_POSITIONS=1)
    stocks = {"A": {"close": a_close, "open": a_close * 1.002, "sig": a_sig, "vol0": [80, 81, 82, 90, 91, 96, 97]},
              "B": {"close": np.full(n, 50.0), "sig": b_sig}}
    md = synth_market("kr", cal, np.full(n, 300.0), stocks)
    Scripted.calls = []
    r = S.run(one_trainer(market="kr", period=(cal[60].date().isoformat(), cal[-1].date().isoformat()), arm="A0",
                          max_positions=1, caps={"마라토너": 0.5}, interest=False, total=100_000_000,
                          universe=("A", "B")), md)
    tr = r["trades"]
    d = lambda k: cal[k].date().isoformat()   # noqa: E731
    check("정지 3일 뒤 첫 거래된 봉 시가에 매수 체결", len(tr) == 1 and tr[0]["entry_date"] == d(83)
          and tr[0]["entry_price"] == a_close[83] * 1.002, f"{tr[0]['entry_date'] if tr else None}")
    check("매도도 정지 뒤 첫 거래된 봉에 체결", tr and tr[0]["exit_date"] == d(98))
    zero = md.zero_volume["A"]
    check("Volume=0 날짜에 체결 없음", not any(f["date"] in zero for f in r["fills"] if f["code"] == "A"))
    check("Volume=0 날짜에 A 판단(신호) 없음", not any(c[0] in zero for c in Scripted.calls if c[1] is not None)
          and all(o["signal_date"] not in zero for o in r["orders"] if o["code"] == "A"))
    check("A 의 매수 대기 주문도 자리로 셈 → B 주문 없음", not any(o["code"] == "B" for o in r["orders"]))
    held = [c for c in Scripted.calls if c[0] == d(95) and c[1] is not None]
    check("days_held 는 그 종목이 거래된 봉만 셈 (83→95 사이 정지 2일 → 10)", held and held[-1][1] == 10,
          f"{held[-1][1] if held else None}")
    bad = accounting(r, md, "kr_v0")
    check("합성 Volume=0 장부 점검", not bad, "; ".join(bad[:3]))


# ================================================================ 8. 이자
@section
def c_interest():
    """8. 이자: 미국 전 거래일 값(빈 날 이월), 국내 m월 = m-1월 값(없으면 이월)"""
    cal = pd.bdate_range("2020-01-01", "2020-12-31")
    n = len(cal)
    days = [d for d in cal if d.strftime("%Y-%m-%d") not in ("2020-07-02", "2020-07-03")]   # 빈 날(휴장 결측) 2개
    vals = []
    for d in days:
        s = d.strftime("%Y-%m-%d")
        v = 0.0 if s < "2020-07-01" else 4.0 if s < "2020-07-06" else 5.0 if s < "2020-09-01" else 2.0
        if s == "2020-10-01":
            v = 50.0                             # 그날 값은 그날 이자에 쓰면 안 됨(다음 거래일에 씀)
        vals.append(v)
    rates = pd.Series(vals, index=pd.DatetimeIndex(days))
    md = synth_market("us", cal, np.full(n, 100.0), {"X": {"close": np.full(n, 10.0)}}, rates, "prev_day")
    r = S.run(S.Config(market="us", period=(cal[60].date().isoformat(), cal[-1].date().isoformat()), arm="A0",
                       with_refs=False), md)
    cash = r["daily"]["cash"].to_numpy()
    i0 = r["i0"]
    ok = True
    first_pos = None
    for k in range(1, len(cash)):
        t = i0 + k
        prev_day = cal[t - 1]
        r_exp = rates[rates.index <= prev_day].iloc[-1]          # 전 거래일 날짜 이하 마지막 값 (점검 쪽 계산)
        if not close(cash[k], cash[k - 1] * (1 + r_exp / 100 / 252), 1e-13, 1e-9):
            ok = False
        if r_exp > 0 and first_pos is None:
            first_pos = cal[t].date().isoformat()
    k0 = cal.searchsorted(pd.Timestamp("2020-07-06"))
    k1 = cal.searchsorted(pd.Timestamp("2020-10-02"))
    check("미국 이자: 매 거래일 현금 × (전 거래일 DTB3)/100/252", ok)
    check("미국 이자: 첫 이자는 7-01 값이 생긴 다음 거래일(7-02)", first_pos == "2020-07-02", first_pos)
    check("미국 이자: 7-06 은 결측(7-02·03) 넘어 7-01 값 4.0 이월, 10-02 에 10-01 값 50 사용",
          md.rate_pct[k0] == 4.0 and md.rate_pct[k1] == 50.0 and md.rate_pct[k1 - 1] == 2.0)
    check("미국 이자: 거래 0번이면 최종 = 시작 + 이자 합", close(r["metrics"]["interest"], r["final"] - r["total"], 1e-9, 1e-6))
    # 국내 월별: 2019-12=1, 2020-01=2, …, 2020-09=10 (10~12월 값 없음)
    calk = pd.bdate_range("2020-01-01", "2020-12-31")
    mon = pd.date_range("2019-12-01", "2020-09-01", freq="MS")
    rk = pd.Series(np.arange(1.0, len(mon) + 1), index=mon)
    mdk = synth_market("kr", calk, np.full(len(calk), 300.0), {"X": {"close": np.full(len(calk), 1000.0)}}, rk,
                       "prev_month")
    # m월 거래일 → m-1월 값: 1월→2019-12(1), 2월→2020-01(2), …, 10월→2020-09(10), 11·12월 → 없으니 9월 값(10) 이월
    table = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9, 10: 10, 11: 10, 12: 10}
    want = np.array([table[d.month] for d in calk], float)
    check("국내 이자율: m월 거래일 = m-1월 값, 11·12월은 값이 없어 9월 값 이월", np.array_equal(mdk.rate_pct, want),
          f"3월={mdk.rate_pct[calk.searchsorted(pd.Timestamp('2020-03-02'))]}, 12월={mdk.rate_pct[-1]}")
    rr = S.run(S.Config(market="kr", period=(calk[60].date().isoformat(), calk[-1].date().isoformat()), arm="A0",
                        with_refs=False), mdk)
    c = rr["daily"]["cash"].to_numpy()
    okk = all(close(c[k], c[k - 1] * (1 + want[rr["i0"] + k] / 100 / 252), 1e-13, 1e-6) for k in range(1, len(c)))
    check("국내 이자: 매 거래일 현금 × (m-1월 값)/100/252", okk)


# ================================================================ 9. 월말 10개월선 전환
@section
def c_trend():
    """9. 월말 10개월선 전환 날짜 (A1-T, G11)"""
    cal = pd.bdate_range("2019-01-01", "2021-12-31")
    n = len(cal)
    t = np.arange(n)
    px = np.where(t < 330, 100 * np.exp(0.002 * t), 100 * np.exp(0.002 * 330) * np.exp(-0.004 * (t - 330)))
    px = np.where(t >= 500, px[499] * np.exp(0.003 * (t - 499)), px)
    md = synth_market("us", cal, px, {"X": {"close": np.full(n, 10.0)}}, idx_open=px * 0.999)
    # 점검 쪽 독립 계산: 월말 = 그 달 마지막 거래일(데이터 마지막 날 제외)
    months = cal.to_period("M")
    me = [k for k in range(n - 1) if months[k + 1] != months[k]]
    mode = ["index"] * n
    cur = "index"
    seen = []
    for k in range(n):
        mode[k] = cur
        if k in me:
            seen.append(px[k])
            if len(seen) >= 10:
                cur = "index" if px[k] > np.mean(seen[-10:]) else "cash"
    i0 = 60
    to_cash = [cal[k].date().isoformat() for k in range(i0 + 1, n) if mode[k] == "cash" and mode[k - 1] == "index"]
    to_idx = [cal[k].date().isoformat() for k in range(i0 + 1, n) if mode[k] == "index" and mode[k - 1] == "cash"]
    first = [cal[i0].date().isoformat()] if mode[i0] == "index" else []
    for arm in ("A1T", "G11"):
        r = S.run(S.Config(market="us", period=(cal[i0].date().isoformat(), cal[-1].date().isoformat()), arm=arm,
                           interest=False, with_refs=False), md)
        sl = next(iter(r["sleeves"]))
        sells = sorted({f["date"] for f in r["fills"] if f["kind"] == "index" and f["side"] == "매도" and f["sleeve"] == sl})
        buys = sorted({f["date"] for f in r["fills"] if f["kind"] == "index" and f["side"] == "매수" and f["sleeve"] == sl})
        check(f"{arm}: 지수→현금 전환 = 월말 다음 거래일 시가 ({len(to_cash)}번)", sells == to_cash and len(to_cash) >= 1,
              f"{sells}")
        check(f"{arm}: 현금→지수 전환 = 월말 다음 거래일 시가 (+첫날 매수)", buys == sorted(first + to_idx) and len(to_idx) >= 1,
              f"{buys}")
        modes = r["daily"][f"mode_{sl}"].tolist()
        check(f"{arm}: 매일 대기 자산 상태 일치(월말 10개 전엔 지수, I3)", modes == mode[i0:], "")


# ================================================================ 10. 단계적 서킷 (H3)
def expected_staged(vals, start, i0):
    """점검 쪽에서 규칙을 따로 다시 계산: 종가 평가액 목록 → (이벤트 [(봉, 종류)], 봉별 절반 여부, 봉별 쉼 여부)."""
    ev, half_at, paused_at = [], {}, {}
    peak, half, paused, pend, prev, stopped = start, False, False, None, None, False
    for k, v in enumerate(vals):
        t = i0 + k
        if stopped:
            break
        if prev is not None and v / prev - 1 <= -0.07:
            ev.append((t, "H3 하루-7% 정지"))
            stopped = True
            paused_at[t] = True
            half_at[t] = half
            break
        skip = False
        if paused:
            if t >= pend:
                paused, peak, half = False, v, True
                ev.append((t, "H3 재개(절반)"))
            else:
                skip = True
        if not skip:
            if v > peak:
                if half:
                    ev.append((t, "H3 원래 상한"))
                peak, half = v, False
            dd = v / peak - 1
            if dd <= -0.20:
                ev.append((t, "H3 -20% 정리"))
                paused, pend, half = True, t + 20, True
            elif dd <= -0.10 and not half:
                half = True
                ev.append((t, "H3 -10% 절반"))
        half_at[t], paused_at[t] = half, paused
        prev = v
    return ev, half_at, paused_at


@section
def c_staged():
    """10. 단계적 서킷(H3)·지금 서킷: 문턱·절반 상한·20거래일 쉼·고점 재설정·하루 -7%"""
    cal = pd.bdate_range("2021-01-04", periods=260)
    n = len(cal)
    k = np.arange(n)
    x = np.where(k < 70, 100.0, 100.0 * 0.97 ** np.clip(k - 69, 0, 41))      # 70~110 매일 -3%
    sx = np.zeros(n)
    sx[61] = 1
    y_sig = np.where(k >= 85, 1.0, 0.0)
    z = np.where(k <= 130, 40.0, 40.0 * 1.01 ** np.clip(k - 130, 0, None))
    z_sig = np.where(k >= 100, 1.0, 0.0)
    w_sig = np.where(k >= 170, 1.0, 0.0)
    stocks = {"X": {"close": x, "sig": sx}, "Y": {"close": np.full(n, 50.0), "sig": y_sig},
              "Z": {"close": z, "sig": z_sig}, "W": {"close": np.full(n, 30.0), "sig": w_sig}}
    md = synth_market("us", cal, np.full(n, 100.0), stocks)
    per = (cal[60].date().isoformat(), cal[-1].date().isoformat())
    cfg = one_trainer(market="us", period=per, arm="A0", cb="staged", caps={"마라토너": 0.3}, interest=False,
                      total=100_000)
    r = S.run(cfg, md)
    vals = r["daily"]["v_마라토너"].to_numpy()
    i0, i1 = r["i0"], r["i1"]
    ev, half_at, paused_at = expected_staged(vals[: i1 - i0], 100_000, i0)          # 마지막 봉은 판단 안 함
    got = [(int(md.cal.searchsorted(pd.Timestamp(e["date"]))), e["kind"]) for e in r["events"]]
    kinds = {kd for _, kd in got}
    check("H3 이벤트(봉·종류)가 점검 쪽 재계산과 같음", got == ev, f"{[(md.dstr[t], kd) for t, kd in got]}")
    check("H3 시나리오가 모든 단계를 지남(-10%·-20%·재개·원래 상한)",
          {"H3 -10% 절반", "H3 -20% 정리", "H3 재개(절반)", "H3 원래 상한"} <= kinds)
    buys = [o for o in r["orders"] if o["action"] == "매수"]
    ok_mult = all(o["cap_mult"] == (0.5 if half_at[o["signal_cal"]] else 1.0) for o in buys)
    ok_pause = not any(paused_at[o["signal_cal"]] for o in buys)
    check("매수 주문의 상한 배수 = 그 종가의 절반 여부 (절반 0.5 / 원래 1.0 둘 다 있음)",
          ok_mult and {o["cap_mult"] for o in buys} == {0.5, 1.0}, f"{[(o['code'], md.dstr[o['signal_cal']], o['cap_mult']) for o in buys]}")
    stop_t = [t for t, kd in ev if kd == "H3 -20% 정리"][0]
    check("-20% 종가 다음 20개 종가(그 봉 포함 t..t+19)엔 매수 주문 없음, t+20 종가에 재개",
          ok_pause and not any(stop_t <= o["signal_cal"] < stop_t + 20 for o in buys)
          and any(o["signal_cal"] == stop_t + 20 for o in buys))
    held_at_stop = [tr["code"] for tr in r["trades"] if tr["entry_cal"] <= stop_t and
                    (tr["exit_cal"] is None or tr["exit_cal"] > stop_t)]
    sold_next = sorted(tr["code"] for tr in r["trades"] if tr["exit_cal"] == stop_t + 1)
    check("-20% 다음 시가에 보유 전부 정리", sorted(held_at_stop) == sold_next and len(sold_next) >= 2, f"{sold_next}")
    fills_ok = all(tr["shares"] == shares_within_cap(100_000, 0.3 * tr["cap_mult"], tr["entry_price"], md.fee, md.slip)
                   for tr in r["trades"])
    check("체결 주식 수 = shares_within_cap(시작 예산, 상한 × 배수, 시가)", fills_ok)
    resume = [e for e in r["events"] if e["kind"] == "H3 재개(절반)"][0]
    check("재개 때 고점 = 그 종가 평가액", close(resume["value"], vals[stop_t + 20 - i0], 0, 1e-9))
    bad = accounting(r, md, "staged")
    check("H3 합성 장부 점검", not bad, "; ".join(bad[:3]))
    # 하루 -7% (기존 규칙 그대로 → 영구 정지), A1 이면 정리 대금은 지수로
    x2 = np.where(k < 80, 100.0, 84.0)                                         # 80 에 하루 -16% (보유 50% → 지갑 -8%)
    s2 = np.zeros(n)
    s2[61] = 1
    md2 = synth_market("us", cal, np.full(n, 100.0),
                       {"X": {"close": x2, "sig": s2}, "Y": {"close": np.full(n, 50.0), "sig": np.where(k >= 70, 1.0, 0)}})
    r2 = S.run(one_trainer(market="us", period=per, arm="A1", cb="staged", caps={"마라토너": 0.5}, interest=False,
                           total=100_000, universe=("X", "Y")), md2)
    e2 = [e for e in r2["events"]]
    check("하루 -7%: 그 종가에 영구 정지 이벤트", len(e2) == 1 and e2[0]["kind"] == "H3 하루-7% 정지"
          and e2[0]["date"] == md2.dstr[80], f"{[(e['date'], e['kind']) for e in e2]}")
    day81 = [f for f in r2["fills"] if f["date"] == md2.dstr[81]]
    check("하루 -7%: 다음 시가에 주식 전부 매도 → 같은 시가에 지수 매수, 그 뒤 매수 주문 없음",
          {(f["kind"], f["side"]) for f in day81} == {("stock", "매도"), ("index", "매수")}
          and not any(o["action"] == "매수" and o["signal_cal"] >= 80 for o in r2["orders"]))
    # 지금 서킷(risk_guard 그대로): 누적 -10% → 영구 정지
    r3 = S.run(one_trainer(market="us", period=per, arm="A0", cb="current", caps={"마라토너": 0.3}, interest=False,
                           total=100_000), md)
    v3 = r3["daily"]["v_마라토너"].to_numpy()
    first = next(k_ for k_ in range(len(v3) - 1) if v3[k_] / 100_000 - 1 <= -0.10) + r3["i0"]
    e3 = r3["events"]
    check("지금 서킷: 누적 -10% 첫 종가에 정지, 그 뒤 매수 주문 없음",
          len(e3) == 1 and e3[0]["date"] == md.dstr[first]
          and not any(o["action"] == "매수" and o["signal_cal"] >= first for o in r3["orders"]),
          f"{[(e['date'], e['kind']) for e in e3]} 예상 {md.dstr[first]}")


# ================================================================ 11. H4
@section
def c_h4():
    """11. H4: 공식, n<20, 실데이터 재배분 재계산, 옮긴 금액 합 0"""
    base = [0.6, 0.3, 0.1]
    rng = np.random.default_rng(1)
    xs19 = [list(rng.normal(0, 0.02, 19)) for _ in range(3)]
    w, ts = S.h4_weights(xs19, base)
    check("H4: n=19 이면 60/30/10 그대로", ts is None and np.allclose(w, base, rtol=0, atol=1e-15))
    xs = [list(rng.normal(m, 0.02, 24)) for m in (0.004, -0.003, 0.0)]
    w, ts = S.h4_weights(xs, base)
    exp = []
    for x, b in zip(xs, base):
        t = statistics.mean(x) / statistics.stdev(x) * math.sqrt(len(x))
        exp.append(b * min(2.0, max(0.25, 1 + 0.25 * t)))
    exp = np.array(exp) / sum(exp)
    check("H4: n=24 몫 = 기본몫 × min(2, max(0.25, 1+0.25t)) 정규화 (t = 평균/표준편차×√n)", np.allclose(w, exp, atol=1e-14),
          f"{np.round(w, 4)}")
    big = [[0.05 + 0.001 * i for i in range(20)], [-0.05 - 0.001 * i for i in range(20)], [0.0] * 20]
    w, ts = S.h4_weights(big, base)
    e = np.array([0.6 * 2.0, 0.3 * 0.25, 0.1 * 1.0])
    check("H4: 클램프(2.0 / 0.25), 표준편차 0 이면 t=0", np.allclose(w, e / e.sum(), atol=1e-14) and ts[2] == 0.0)
    md = S.get_market("us")
    a = S.run(S.Config(market="us", period="2018 조정", arm="A1", with_refs=False))
    h = S.run(S.Config(market="us", period="2018 조정", arm="A1", realloc=True, with_refs=False))
    check("H4: 20개월이 안 되는 국면(2018)은 A1 과 완전히 같음",
          h["fills"] == a["fills"] and np.array_equal(h["equity"], a["equity"]))
    r = S.run(S.Config(market="us", period="2015-17 상승", arm="A1", realloc=True, with_refs=False))
    names = list(S.TRAINERS)
    ok_w, ok_move, nchg = True, True, 0
    for e in [e for e in r["events"] if e["kind"] == "H4"]:
        xs = [[rk - ri for d, rk, ri in r["sleeves"][nm]["monthly"] if d < e["date"]] for nm in names]
        if len(xs[0]) != e["n_months"]:
            ok_w = False
        if len(xs[0]) < 20:
            exp = np.array(base)
        else:
            exp = []
            for x, b in zip(xs, base):
                t = statistics.mean(x) / statistics.stdev(x) * math.sqrt(len(x))
                exp.append(b * min(2.0, max(0.25, 1 + 0.25 * t)))
            exp = np.array(exp) / sum(exp)
        if not np.allclose([e["w_new"][nm] for nm in names], exp, atol=1e-12):
            ok_w = False
        if e["changed"]:
            nchg += 1
            if abs(sum(e["moved"].values())) > 1e-6 * e["V"]:
                ok_move = False
            if not close(sum(e["post"].values()), e["V"], 1e-12, 1e-6):
                ok_move = False
            if not e["short"]:          # 지수가 넉넉했으면 옮긴 뒤 평가액 = 새 몫 × 합계
                if any(not close(e["post"][nm], e["w_new"][nm] * e["V"], 1e-9, 1e-6) for nm in names):
                    ok_move = False
            else:                       # 모자랐으면 주는 쪽은 지수 전부, 받는 쪽은 모자란 비율대로
                gap = {nm: e["w_new"][nm] * e["V"] - e["pre"][nm] for nm in names}
                recv = [nm for nm in names if gap[nm] > 0]
                tot_gap = sum(gap[nm] for nm in recv)
                got = sum(e["moved"].get(nm, 0) for nm in recv)
                if any(not close(e["moved"].get(nm, 0), got * gap[nm] / tot_gap, 1e-9, 1e-6) for nm in recv):
                    ok_move = False
    check("H4 실데이터(2015-17): 분기 첫날마다 몫 = 지난 월 초과수익으로 다시 계산한 값", ok_w and nchg >= 1,
          f"몫 바뀐 분기 {nchg}번")
    nshort = sum(1 for e in r["events"] if e["kind"] == "H4" and e["changed"] and e["short"])
    check("H4: 옮긴 금액 합 = 0, 옮긴 뒤 = 새 몫 × 합계(지수 모자라면 가능한 만큼, 받는 쪽은 비율대로)", ok_move,
          f"지수 모자란 분기 {nshort}번")
    # 월 수익률 재계산(재배분이 없는 달): r = 월말 평가 / 전 월말 평가 - 1, 첫 달은 시작 금액 기준
    chg_months = {e["date"][:7] for e in r["events"] if e["kind"] == "H4" and e["changed"]}
    d = r["daily"]
    ok_m = True
    for nm in names:
        prev_v, prev_i = r["sleeves"][nm]["start_cash"], md.idx_open[r["i0"]]
        for dt, rk, ri in r["sleeves"][nm]["monthly"]:
            v = d.loc[dt, f"v_{nm}"]
            ic = md.idx_close[md.dstr.index(dt)]
            if dt[:7] not in chg_months and not (close(rk, v / prev_v - 1, 1e-9, 1e-12) and close(ri, ic / prev_i - 1, 1e-12, 1e-14)):
                ok_m = False
            prev_v, prev_i = v, ic
    check("H4: 월 수익률(트레이너·지수)을 일별 평가로 다시 계산해도 같음", ok_m)
    first = min(e["date"] for e in r["events"] if e["kind"] == "H4" and e["changed"])
    a2 = S.run(S.Config(market="us", period="2015-17 상승", arm="A1", with_refs=False))
    check("H4: 첫 재배분 전까지는 A1 과 체결이 같음",
          [f for f in r["fills"] if f["date"] < first] == [f for f in a2["fills"] if f["date"] < first])
    bad = accounting(r, md, "h4")
    check("H4 장부 점검(2015-17)", not bad, "; ".join(bad[:3]))


# ================================================================ 12. 무작위 대조
@section
def c_random():
    """12. 무작위 대조(H1-4): 제자리 = 실제 합, 재현, 범위, 거래 하나 손계산"""
    md = S.get_market("us")
    r = S.run(S.Config(market="us", period="2018 조정", arm="A1", with_refs=False))
    c = S.Contribution(md, r)
    act = c.actual()
    same = c.per_trade(np.tile(c.e, (4, 1))).sum(axis=1)
    rc = S.random_control(md, r, 50, 7)
    check("모든 거래를 제자리에 둔 '무작위' 합 = 실제 합", np.all(same == act.sum()) and rc["전체"]["actual"] == act.sum(),
          f"거래 {len(act)}건")
    e1, e2 = c.draws(30, 99), c.draws(30, 99)
    check("같은 시드면 같은 무작위 진입, 모두 [가능한 첫 봉, 마지막 봉] 안", np.array_equal(e1, e2)
          and np.all((e1 >= c.lo) & (e1 <= c.hi)))
    tr = r["trades"][0]
    st = md.by_code[tr["code"]]
    N = tr["shares"] * tr["entry_price"]
    if tr["exit_own"] is not None:
        gs = st.open[tr["exit_own"]] / tr["entry_price"]
        gi = md.idx_open[tr["exit_cal"]] / md.idx_open[tr["entry_cal"]]
        cb = (1 + md.slip) * (1 + md.fee) - 1
        cs = 1 - (1 - md.slip) * (1 - md.fee)
        hand = N * (gs - gi) - N * (cb + cs) - N * gs * (cs + cb)
    else:
        hand = float("nan")
    check("거래 하나 손계산 = 기여 함수", close(hand, act[0], 1e-12, 1e-9), f"{hand:.6f} vs {act[0]:.6f}")


# ================================================================ 13. 스모크 (실데이터, 2018 한 국면)
SMOKE = [dict(arm="A0"), dict(arm="A1"), dict(arm="A1T"), dict(arm="A2"), dict(arm="G11"),
         dict(arm="A0", cb="current"), dict(arm="A0", cb="staged"), dict(arm="A1", cb="current"),
         dict(arm="A1", cb="staged"), dict(arm="A1", realloc=True)]


@section
def c_smoke():
    """13. 스모크: 3시장 × 10설정 × 2018 — 예외·NaN 없음 + 장부 점검 (숫자는 '돌았나'만)"""
    timing = {}
    for key in ("us", "us_pit", "kr"):
        md = S.get_market(key)
        t0 = time.time()
        for a in SMOKE:
            t = time.time()
            nr = 1000 if (a == dict(arm="A1")) else 0
            r = S.run(S.Config(market=key, period="2018 조정", n_random=nr, **a))
            timing[(key, S.label(r["config"]))] = time.time() - t
            print("    " + S.sanity_line(r), flush=True)
            bad = accounting(r, md, key)
            check(f"스모크 {key} {S.label(r['config'])}: 예외·NaN 없음, 장부 OK", not bad, "; ".join(bad[:3]))
            if nr:
                rd = r["random"]
                okr = rd["n_draws"] == 1000 and all(0 <= rd[g]["pct_below"] <= 1 and math.isfinite(rd[g]["random_mean"])
                                                     for g in rd if isinstance(rd[g], dict))
                check(f"스모크 {key} A1 무작위 대조 1,000번 돌았음(값은 2단계에서 봄)", okr, f"거래 {rd['n_trades']}건")
            refs = r.get("refs", {})
            okref = all(math.isfinite(refs[k]["return"]) for k in refs)
            check(f"스모크 {key} {S.label(r['config'])}: 참고선(지수 B&H·동일비중 B&H·G11) 계산됨", okref)
        print(f"    {key}: 10설정 {time.time() - t0:.1f}s (판단 호출 {md.decide_calls:,}번)", flush=True)
        if key == "kr":
            zero_fills = sum(1 for f in r["fills"] if f["kind"] == "stock" and f["date"] in md.zero_volume.get(f["code"], ()))
            check("스모크 kr: 2018 정지 종목(005930·035420·207940)이 있어도 Volume=0 날 체결 0", zero_fills == 0)
            r0 = S.run(S.Config(market="kr", period="2018 조정", arm="A0", with_refs=False))
            a6 = S.a6_split_volume_buys(md, r0)
            check("스모크 kr: A6 보고(분할 정지 뒤 20봉 파이오니어 거래량 신호 매수 수) 계산됨",
                  set(a6) == set(S.A6_SPLIT_SUSPENSIONS), str({k: (v["after"], v["pioneer_buys"]) for k, v in a6.items()}))
    return timing


def main():
    t = time.time()
    c_r0_equivalence()
    c_window_kr()
    c_index_identities()
    c_kr_tax()
    c_kr_zero_volume()
    c_interest()
    c_trend()
    c_staged()
    c_h4()
    c_random()
    c_smoke()
    c_lookahead()
    n_fail = sum(1 for _, ok in RESULTS if not ok)
    print(f"\n합계: PASS {len(RESULTS) - n_fail} / FAIL {n_fail}  ({time.time() - t:.0f}s)")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
